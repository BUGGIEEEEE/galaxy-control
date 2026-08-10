# Galaxy Control for Codex

macOS의 Codex가 Samsung Galaxy를 **관찰 → 최소 조작 → 독립 검증** 순서로 다루도록 만든
배포용 스킬입니다.

```text
사용자 요청
   ↓
Codex + galaxy-control
   ├─ OpenMinis ─ 의미·글자·버튼 관찰과 반복 가능한 조작
   ├─ scrcpy ──── 실시간 화면, 드래그, 회전, 복합 제스처
   └─ ADB/Shizuku ─ 기기 신원·연결·시스템 사실
   ↓
다른 적절한 경로로 결과 확인 후 다음 단계
```

## 지원 범위

- macOS
- Samsung Galaxy 한 대
- Codex desktop와 필요한 Computer Use 권한
- 이미 설치되어 정상 동작하는 호환 OpenMinis Control v2
- Tailscale을 통한 기기 간 연결
- ADB와 scrcpy
- Android 공식 Wireless Debugging

OpenMinis 설치·업데이트·활성화는 이 배포판이 수행하지 않습니다. Galaxy 재부팅 후 완전
무인 복구도 지원하지 않으며, Android가 요구하는 잠금 해제와 보안 설정은 사용자가 직접
확인해야 합니다.

## 설치

공개 릴리스 태그를 고정해 내려받습니다.

```sh
git clone --depth 1 --branch v0.1.3 https://github.com/BUGGIEEEEE/galaxy-control.git
cd galaxy-control
python3 scripts/install_skill.py --approved
```

설치기는 기존 `galaxy-control` 스킬을 덮어쓰지 않습니다. 이미 설치되어 있으면 중단하므로
기존 스킬의 백업·교체 여부를 사용자가 먼저 결정해야 합니다. 설치 뒤 Codex를 새로 열고
`$galaxy-control`을 호출합니다.

`uv`가 없는 새 Mac은 저장소 안의 표준 Python 부트스트랩으로 먼저 확인합니다.

```sh
python3 scripts/bootstrap.py doctor
python3 scripts/bootstrap.py apply --approved
```

두 번째 명령은 `uv`가 없고 Homebrew가 있을 때만 정확히 `brew install uv`를 실행합니다.
Homebrew도 없으면 자동 설치하지 않고 사용자가 Homebrew 또는 uv를 설치하도록 중단합니다.

## 최초 환경 구성

먼저 읽기 전용 진단과 계획만 실행합니다.

```sh
GALAXY_SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/galaxy-control"
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" doctor
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" plan
```

계획에 표시된 Homebrew 명령을 확인한 뒤에만 다음을 실행합니다.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" apply --approved
```

자동 설치 대상은 **현재 없는** ADB, scrcpy, `uv`뿐입니다. 이미 있는 도구는 업데이트하지
않습니다. Tailscale 설치·로그인/VPN 승인, macOS 개인정보 보호 창, Galaxy 잠금 해제,
ADB 신뢰, Wireless Debugging, Accessibility와 Shizuku 권한은 보안상 사용자가 진행합니다.

Galaxy 한 대를 USB로 연결하고 잠금 해제한 뒤 등록합니다.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enroll --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py"
```

두 대 이상이면 doctor의 현재 목록에서 정확한 대상을 고른 뒤
`enroll --serial LIVE_SERIAL --approved`를 사용합니다. 등록 정보는 Git 저장소가 아니라
사용자 전용 Application Support 파일에 비공개 권한으로 저장됩니다.

## 주요 인터페이스

```sh
# OpenMinis
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" health
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" ui-info

# scrcpy
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" view
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" control
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" stop

# ADB 상태와 공식 Wireless Debugging
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" status
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-status
```

모든 명령은 임의 옵션을 받지 않는 고정 프로필입니다. 페어링, `adb tcpip`, 네트워크·권한
변경, 재부팅, 전송·결제·삭제는 별도의 명시적 승인이 필요합니다.

## 배포 완성도

- 자동 테스트와 정적·프라이버시 검사를 통과한 릴리스: `PACKAGE_READY`
- 새로운 사용자의 깨끗한 Mac 설치 확인: `PILOT_INSTALL_VERIFIED`
- 새로운 사용자의 실제 화면·입력·독립 검증까지 확인: `PILOT_E2E_VERIFIED`
- 위 검증과 공개 태그·체크섬까지 모두 확인: `DISTRIBUTION_READY`

코드 테스트만으로 실제 다른 사용자의 Galaxy 제어 성공을 주장하지 않습니다. 상세 설계는
[Master Plan](docs/MASTER_PLAN.md)과 [단계별 계획](docs/plans/)에 있습니다.

## 제거

스킬 디렉터리와 Galaxy Control이 만든 두 로컬 상태 디렉터리만 사용자가 명시적으로
제거할 수 있습니다.

```text
~/.codex/skills/galaxy-control
~/Library/Application Support/galaxy-control
~/Library/Caches/galaxy-control
```

제거는 OpenMinis, Tailscale, Galaxy 데이터, 녹화 출력, ADB 키를 삭제하지 않습니다.
보안 정책과 취약점 제보 방법은 [SECURITY.md](SECURITY.md)를 확인하세요.
