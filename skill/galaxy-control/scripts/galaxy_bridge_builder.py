"""Build one content-addressed OpenMinis Control v2 installer package."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import ipaddress
import json
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

TAILNET: Final = ipaddress.IPv4Network("100.64.0.0/10")
MAX_ARTIFACT_BYTES: Final = 262_144
PRIVATE_FILE_MODE: Final = 0o600
TEMPLATE_NAME: Final = "installer_template.py"
RUNTIME_FILES: Final = (
    "openminis_bridge_control.py",
    "openminis_bridge_control_lifecycle.py",
    "openminis_bridge_control_process.py",
    "openminis_bridge_control_core/__init__.py",
    "openminis_bridge_control_core/actions.py",
    "openminis_bridge_control_core/http_api.py",
    "openminis_bridge_control_core/network.py",
    "openminis_bridge_control_core/protocol.py",
    "openminis_bridge_control_core/requests.py",
)


@dataclass(frozen=True, slots=True)
class BridgePackageError(Exception):
    """One safe package-building failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class BridgeIdentity(BaseModel):
    """Validated per-user tailnet identity embedded only in a local artifact."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    phone_ipv4: str
    trusted_mac_ipv4: str
    port: Annotated[int, Field(ge=1, le=65535)] = 43129

    @field_validator("phone_ipv4", "trusted_mac_ipv4")
    @classmethod
    def parse_tailnet_address(cls, raw: str) -> str:
        """Accept only one literal IPv4 address from the Tailscale CGNAT range."""
        try:
            address = ipaddress.IPv4Address(raw)
        except ipaddress.AddressValueError as error:
            raise PydanticCustomError("tailnet_ipv4", "must be a literal IPv4 address") from error
        if address not in TAILNET:
            raise PydanticCustomError("tailnet_ipv4", "must be inside 100.64.0.0/10")
        return str(address)

    @model_validator(mode="after")
    def require_distinct_peers(self) -> BridgeIdentity:
        """Reject a profile that mistakes the phone for the trusted Mac."""
        if self.phone_ipv4 == self.trusted_mac_ipv4:
            raise PydanticCustomError("tailnet_identity", "phone and Mac must be distinct peers")
        return self


@dataclass(frozen=True, slots=True)
class BridgePackage:
    """Deterministic personalized installer and non-secret verification metadata."""

    artifact_name: str
    artifact: bytes
    artifact_sha256: str
    manifest_sha256: str
    install_instruction: str
    lifecycle_instruction: str


def _read_assets(asset_root: Path) -> dict[str, bytes]:
    """Read the exact reviewed runtime allowlist and reject link substitution."""
    if not asset_root.is_absolute() or not asset_root.is_dir() or asset_root.is_symlink():
        raise BridgePackageError("bridge_assets_invalid", "bridge asset root is unavailable")
    files: dict[str, bytes] = {}
    for name in RUNTIME_FILES:
        path = asset_root / name
        if not path.is_file() or path.is_symlink():
            raise BridgePackageError(
                "bridge_assets_invalid", f"required bridge asset missing: {name}"
            )
        try:
            files[name] = path.read_bytes()
        except OSError as error:
            raise BridgePackageError(
                "bridge_assets_invalid", "bridge asset cannot be read"
            ) from error
    return files


def _manifest(files: Mapping[str, bytes]) -> tuple[str, str]:
    manifest = {
        name: [len(content), hashlib.sha256(content).hexdigest()] for name, content in files.items()
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def _archive(files: Mapping[str, bytes]) -> bytes:
    """Create a byte-for-byte reproducible gzip-compressed tar archive."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT) as bundle:
        for name in sorted(files):
            content = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = PRIVATE_FILE_MODE
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            bundle.addfile(info, io.BytesIO(content))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
        _ = stream.write(tar_buffer.getvalue())
    return compressed.getvalue()


def _replace_once(template: str, marker: str, value: str) -> str:
    if template.count(marker) != 1:
        raise BridgePackageError("bridge_template_invalid", f"invalid template marker: {marker}")
    return template.replace(marker, value)


def _render_installer(
    identity: BridgeIdentity,
    template: str,
    manifest_json: str,
    manifest_sha256: str,
    archive: bytes,
) -> tuple[bytes, str]:
    identity_json = identity.model_dump_json()
    approval_binding = hashlib.sha256(
        b"openminis-control-v2\0"
        + identity_json.encode()
        + b"\0"
        + manifest_sha256.encode()
        + b"\0"
        + hashlib.sha256(archive).digest()
    ).hexdigest()
    replacements = {
        "__PHONE_IPV4__": identity.phone_ipv4,
        "__TRUSTED_MAC_IPV4__": identity.trusted_mac_ipv4,
        "__PORT__": str(identity.port),
        "__APPROVAL_BINDING__": approval_binding,
        "__MANIFEST_SHA256__": manifest_sha256,
        "__MANIFEST_JSON__": manifest_json,
        "__ARCHIVE_B64__": base64.b64encode(archive).decode("ascii"),
    }
    rendered = template
    for marker, value in replacements.items():
        rendered = _replace_once(rendered, marker, value)
    artifact = rendered.encode()
    if len(artifact) >= MAX_ARTIFACT_BYTES:
        raise BridgePackageError("bridge_artifact_too_large", "bridge artifact exceeds safe limit")
    return artifact, approval_binding


def _install_instruction(
    artifact_name: str,
    artifact_size: int,
    artifact_sha256: str,
    approval_binding: str,
) -> str:
    launcher = (
        '/usr/bin/env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin TMPDIR=/tmp '
        "LANG=C.UTF-8 LC_ALL=C.UTF-8 python3 -I -B -c '# fmt: off\n"
        "import fcntl,hashlib as x,os,re,sys\n"
        'o=os;a=re.fullmatch;p,z,h,m,v=sys.argv[1:];n=int(z);assert sys.platform=="linux"'
        'and 0<n<262145 and a("[0-9a-f]{64}",h)and a("INSTALL_ONCE",m)'
        'and a("[0-9a-f]{64}",v)\n'
        "f=o.open(p,655360);s=o.fstat(f);b=o.read(f,n+1);assert(s[0]>>12,s[4],s[3],"
        "s[0]&18,s[6],len(b),x.sha256(b).hexdigest())==(8,o.getuid(),1,0,n,n,h);"
        "assert s[:7]==o.lstat(p)[:7]\n"
        'e=o.memfd_create("",3);assert o.write(e,b)==n;_=fcntl.fcntl(e,1033,15);'
        "_=o.lseek(e,0,0);c=o.read(e,n+1);assert c==b\n"
        'q=f"<sealed-memory:{h}>";sys.argv=[q,m,v];exec(compile(c,q,"exec",dont_inherit=True))\n'
        "' "
        f"/var/minis/attachments/uploads/{artifact_name} {artifact_size} {artifact_sha256} "
        f"INSTALL_ONCE {approval_binding}"
    )
    return (
        "# Minis에서 OpenMinis Control v2 설치\n\n"
        f"1. `{artifact_name}` 파일 하나만 Minis 대화에 첨부합니다.\n"
        "2. 아래 명령을 정확히 한 번 실행하도록 지시합니다. 실패하면 반복하지 말고 JSON 오류를 반환합니다.\n\n"
        "```bash\n"
        f"{launcher}\n"
        "```\n\n"
        f"예상 파일 SHA-256: `{artifact_sha256}`\n"
    )


def _lifecycle_instruction() -> str:
    entrypoint = "$HOME/.local/share/openminis-bridge-control/openminis_bridge_control.py"
    return (
        "# OpenMinis Control v2 로컬 브리지 관리\n\n"
        "Minis의 로컬 실행 기능에서 필요한 명령 하나만 정확히 실행합니다.\n\n"
        "```bash\n"
        f"python3 -E -s -B {entrypoint} status\n"
        f"python3 -E -s -B {entrypoint} start\n"
        f"python3 -E -s -B {entrypoint} stop\n"
        "```\n\n"
        "평상시는 `status`를 먼저 실행하고, 중지된 경우에만 `start`를 한 번 실행합니다.\n"
    )


def build_bridge_package(identity: BridgeIdentity, asset_root: Path) -> BridgePackage:
    """Build one deterministic package from reviewed bridge assets."""
    files = _read_assets(asset_root)
    manifest_json, manifest_sha256 = _manifest(files)
    archive = _archive(files)
    template_path = asset_root / TEMPLATE_NAME
    if not template_path.is_file() or template_path.is_symlink():
        raise BridgePackageError("bridge_template_invalid", "bridge installer template is missing")
    try:
        template = template_path.read_text()
    except OSError as error:
        raise BridgePackageError(
            "bridge_template_invalid", "bridge template cannot be read"
        ) from error
    artifact, approval_binding = _render_installer(
        identity,
        template,
        manifest_json,
        manifest_sha256,
        archive,
    )
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    artifact_name = f"openminis-control-v2-{artifact_sha256}.py"
    return BridgePackage(
        artifact_name=artifact_name,
        artifact=artifact,
        artifact_sha256=artifact_sha256,
        manifest_sha256=manifest_sha256,
        install_instruction=_install_instruction(
            artifact_name,
            len(artifact),
            artifact_sha256,
            approval_binding,
        ),
        lifecycle_instruction=_lifecycle_instruction(),
    )
