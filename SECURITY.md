# Security policy

## Supported versions

보안 수정은 최신 공개 릴리스에 제공됩니다. 설치할 때 릴리스 태그와 게시된 SHA-256을
확인하세요.

## Report a vulnerability

공개 이슈에 토큰, 페어링 코드, ADB 키, 기기 serial, Tailscale IP, 개인 화면, 로그 또는
녹화 파일을 올리지 마세요. GitHub 저장소의 비공개 Security Advisory 기능으로 재현 단계와
영향 범위만 보내 주세요.

## Security model

- 기기 serial, 모델, Tailscale 주소는 공개 코드가 아니라 사용자 전용 `0600` 프로필에
  저장됩니다.
- 공개 저장소에는 Galaxy/Mac Tailscale 주소나 OpenMinis 토큰을 넣지 않습니다.
- 개인화 설치 파일은 등록 프로필과 Mac의 현재 Tailscale 주소를 자동으로 넣으므로 `0600`
  파일로 생성되며 대상 Galaxy의 Minis에만 전달해야 합니다.
- OpenMinis Control v2 토큰은 Galaxy에서 설치할 때 생성되고 `0600` 파일로만 저장되며,
  설치 결과·명령행·로그에 출력하지 않습니다.
- Wireless Debugging pairing code는 stdin에서 한 번만 읽으며 argv, 환경, 파일, JSON, 로그에
  저장하지 않습니다.
- ADB와 scrcpy는 검토된 argv 배열과 `shell=False`만 사용합니다.
- scrcpy는 저장된 전체 프로세스 신원이 맞는 경우에만 해당 PID를 종료합니다.
- OpenMinis 설치·업데이트·활성화·reconcile과 범용 원격 셸은 제공하지 않습니다.

## Personalized bridge handoff

공개 브리지 런타임은 개인 주소를 포함하지 않습니다. `galaxy_bridge_package.py build`가 다음
검증된 값만 개인화 설치 파일에 넣습니다.

- 등록된 Galaxy 프로필의 Tailscale IPv4와 OpenMinis 포트
- Mac에서 정확히 하나만 확인된 별도의 Tailscale IPv4

임의 host, IP, 포트, 셸 인자를 받지 않으며 출력 폴더는 기존 경로를 덮어쓰지 않습니다.
생성된 설치 파일은 Git 추적 대상이 아니며 공개 배포물이 아닙니다. 설치 파일은 내용 기반
SHA-256 이름을 사용하고, Minis에서는 `INSTALL.md`의 sealed-memory 실행기만 한 번 사용합니다.

## Fixed TCP ADB warning

선택 기능인 TCP ADB `5555`는 Tailscale 인터페이스에만 묶인다고 보장할 수 없습니다. Wi-Fi가
켜져 있으면 같은 LAN에서 포트 접근을 시도할 수 있고, Tailscale ACL은 로컬 LAN 직접 접근을
차단하지 않습니다. ADB RSA 인증은 필요하지만 포트 번호 변경은 실질적인 보안 통제가
아닙니다. 새 프로필에서는 기본적으로 비활성화됩니다.

## Release privacy gate

공개 릴리스 전에 현재 파일과 전체 Git 패치를 검사합니다.

```sh
python3 scripts/privacy_scan.py --history
```

검사기는 발견된 민감 문자열 자체를 다시 출력하지 않고 파일·줄·규칙만 보고합니다. 실제
사용자 값을 알고 있는 배포 담당자는 별도의 정확한 denylist 검색도 수행해야 합니다.
