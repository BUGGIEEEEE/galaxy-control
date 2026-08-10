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
- OpenMinis 토큰이 필요한 호환 환경에서는 프로세스 환경에서만 읽고 출력하지 않습니다.
- Wireless Debugging pairing code는 stdin에서 한 번만 읽으며 argv, 환경, 파일, JSON, 로그에
  저장하지 않습니다.
- ADB와 scrcpy는 검토된 argv 배열과 `shell=False`만 사용합니다.
- scrcpy는 저장된 전체 프로세스 신원이 맞는 경우에만 해당 PID를 종료합니다.
- OpenMinis 설치·업데이트·활성화·reconcile과 범용 원격 셸은 제공하지 않습니다.

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
