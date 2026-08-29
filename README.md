# Galaxy Control for Codex

macOS의 Codex가 Samsung Galaxy를 **관찰 → 최소 조작 → 독립 검증** 순서로 다루도록 만든
배포용 스킬입니다.

```text
사용자 요청
   ↓
Codex + galaxy-control
   ├─ 세션 최초 전체 진단 → 기존 페어링 ADB 복구 시도
   ├─ 후속 작업 유형 판단 → 관련 경로만 사전검사
   ├─ OpenMinis ─ 의미·글자·버튼 관찰과 반복 가능한 조작
   ├─ scrcpy ──── 실시간 화면, 드래그, 회전, 복합 제스처
   └─ ADB/Shizuku ─ 기기 신원·연결·시스템 사실
   ↓
최소 조작 → 실제 사용 경로 기록 → 새 상태로 결과 검증
```

## 한눈에 보는 연동 구조

### 1. Codex와 Galaxy가 동작하는 흐름

![Codex와 Galaxy의 선택적 사전검사·조작·검증 흐름](docs/images/galaxy-flow-1-v040.svg)

### 2. 처음 연결하는 흐름

![Mac과 Galaxy의 USB 신원 기반 최초 설정 흐름](docs/images/galaxy-flow-2-v040.svg)

### 3. Codex와 사용자가 맡는 단계

![Galaxy 연결 설정의 Codex와 사용자 역할 및 세션 정책](docs/images/galaxy-flow-3-v040.svg)

그림은 역할과 순서를 설명하는 일반화 자료입니다. 실제 기기 serial, IP, 토큰, 페어링
코드는 포함하지 않습니다. 페어링 포트와 연결 포트는 서로 다른 현재값이며, 6자리 페어링
코드는 사용자가 ADB의 표준 입력에 직접 입력하고 채팅·파일·로그에 남기지 않습니다.
사전검사 결과는 현재 에이전트 세션에서만 재사용되고 디스크에 저장되지 않습니다. 최초
세션 준비는 ADB가 없을 때 등록된 mDNS 서비스 하나로 기존 페어링 연결을 한 번 복구하고,
실패해도 OpenMinis 경로를 차단하지 않습니다. 최초 기기 등록은 ADB 목록에서 물리적인
`usb:` 연결이 확인된 Galaxy만 허용합니다.

## 지원 범위

- macOS
- Samsung Galaxy 한 대
- Codex desktop와 필요한 Computer Use 권한
- Galaxy에 설치된 OpenMinis와 이 저장소에서 생성하는 OpenMinis Control v2 로컬 브리지
- Tailscale을 통한 기기 간 연결
- ADB와 scrcpy
- Android 공식 Wireless Debugging

OpenMinis 앱이나 APK 설치·업데이트는 이 배포판이 수행하지 않습니다. 대신 일반 OpenMinis
앱만으로는 제공되지 않는 Control v2 브리지 소스와 개인화 설치 파일 생성기를 포함합니다.
Galaxy 재부팅 후 완전
무인 복구도 지원하지 않으며, Android가 요구하는 잠금 해제와 보안 설정은 사용자가 직접
확인해야 합니다.

## 설치

공개 릴리스 태그를 고정해 내려받습니다.

```sh
git clone --depth 1 --branch v0.5.2 https://github.com/BUGGIEEEEE/galaxy-control.git
cd galaxy-control
python3 scripts/install_skill.py --approved
```

새 설치에는 위 명령을 사용합니다. 기존 설치를 승인된 최신 릴리스로 교체할 때는 다음
원자적 업그레이드 명령을 사용합니다.

```sh
python3 scripts/install_skill.py --upgrade --approved
```

업그레이드는 새 스킬을 먼저 별도 경로에 복사한 뒤 기존 설치를 비공개
`.galaxy-control-backups` 디렉터리로 이동하고 새 버전을 활성화합니다. v0.5.2 업그레이드는
사용자 소유의 기존 `~/Library/Caches/galaxy-control`이 있으면 심볼릭 링크가 아님을 확인한
뒤 권한을 `0700`으로 강화합니다. 활성화에 실패하면
기존 설치를 즉시 복구하며, 성공한 경우 출력된 백업 경로를 수동 롤백용으로 유지합니다.
Application Support의 기기 프로필과 ADB 키는 스킬 디렉터리 밖에 있으므로 변경하지
않습니다. 설치 뒤 Codex를 새로 열고 `$galaxy-control`을 호출합니다.

### 기존 스킬이 설치된 사용자

기존 스킬을 삭제·이동·덮어쓰지 않아도 브리지 준비를 먼저 진행할 수 있습니다. `v0.5.2`
저장소를 별도 폴더에 내려받고, 아래처럼 **체크아웃 안의 배포용 스킬 경로**를 사용합니다.

```sh
git clone --depth 1 --branch v0.5.2 https://github.com/BUGGIEEEEE/galaxy-control.git galaxy-control-v0.5.2
cd galaxy-control-v0.5.2
BRIDGE_RELEASE_ROOT="$PWD/skill/galaxy-control"

uv run "$BRIDGE_RELEASE_ROOT/scripts/galaxy_bridge_package.py" doctor
uv run "$BRIDGE_RELEASE_ROOT/scripts/galaxy_bridge_package.py" \
  build --output "$HOME/Desktop/openminis-control-v2-handoff" --approved
```

이 명령은 기존에 설치된 `~/.codex/skills/galaxy-control`을 수정하지 않습니다. 등록 프로필은
기존 Application Support 위치에서 읽고, 새 개인화 인계 폴더만 만듭니다. 브리지 E2E 확인 후
스킬 자체를 `v0.5.2`로 교체할지는 별도 작업으로 결정하세요. 설치기는 의도적으로 자동
업그레이드하지 않습니다.

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
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
```

최초 세션에서 이미 페어링된 ADB를 자동 복구하려면 한 번 명시적으로 opt-in합니다.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enable-auto-reconnect --approved
```

언제든 `disable-auto-reconnect --approved`로 해제할 수 있습니다. 이 설정은 자동 페어링,
Wireless Debugging 변경, 포트 검색 또는 고정 TCP ADB를 허용하지 않습니다.

두 대 이상이면 doctor의 현재 목록에서 정확한 대상을 고른 뒤
`enroll --serial LIVE_SERIAL --approved`를 사용합니다. 등록 정보는 Git 저장소가 아니라
사용자 전용 Application Support 파일에 비공개 권한으로 저장됩니다.

## OpenMinis Control v2 브리지 준비

일반 OpenMinis 앱이 설치되어 있어도 포트 `43129`의 Control v2 브리지는 별도로 준비해야
합니다. 공개 소스 파일의 IP를 직접 수정하지 않습니다. 상대방 Codex가 아래 세 값을 자동으로
확인해 **그 사용자에게만 맞는 설치 파일**을 Mac에서 생성합니다.

| 값 | 어디서 읽는가 | 어디에 채워지는가 |
| --- | --- | --- |
| Galaxy Tailscale IPv4 | `enroll`이 만든 비공개 기기 프로필 | 생성된 설치 파일 → Galaxy의 비공개 `bridge.json` |
| Mac Tailscale IPv4 | Mac의 `tailscale ip -4` 실시간 결과 | 생성된 설치 파일 → Galaxy의 비공개 `bridge.json` |
| 포트 | 비공개 프로필의 `openminis_port` | 기본값 `43129`; 생성된 설치 파일과 `bridge.json` |

먼저 값과 공개 브리지 자산을 읽기 전용으로 검사합니다.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" doctor
```

`READY`이면 비어 있는 절대 경로 하나를 골라 개인화 인계 묶음을 만듭니다.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" \
  build --output "$HOME/Desktop/openminis-control-v2-handoff" --approved
```

생성 폴더에는 다음 네 종류만 있습니다.

- `openminis-control-v2-<SHA256>.py`: 해당 Galaxy/Mac 조합 전용 설치 파일
- `INSTALL.md`: Minis에게 파일을 첨부한 뒤 정확히 한 번 실행시킬 지시문
- `LIFECYCLE.md`: `status`, `start`, `stop` 고정 명령
- `SHA256SUMS`: 설치 파일과 포함된 런타임 manifest 확인값

상대방 Codex는 `INSTALL.md`대로 설치한 뒤 `LIFECYCLE.md`의 `status`를 확인하고, Mac에서
다음을 실행해 실제 연결을 검증합니다.

```sh
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" health
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" a11y-status
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" ui-info
```

## 재부팅 뒤 세션 준비

사용자는 Galaxy 잠금을 해제하고 Wi-Fi·Tailscale, OpenMinis Control v2 브리지, 필요한
Shizuku 권한을 준비합니다. 그 뒤 Galaxy Control의 첫 작업은 다음 순서를 자동으로
수행합니다.

```sh
# 모든 프로필
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" all

# steady_adb_enabled=true일 때만 먼저 고정 endpoint 확인
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" connect

# ADB가 없고 auto_reconnect_adb_enabled=true일 때만 동적 bootstrap
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved

# steady_adb_enabled=true이고 동적 endpoint가 검증됐을 때만 5555로 승격
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" \
  legacy-enable-from-wireless --port CURRENT_CONNECTION_PORT --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" connect

# 프로필이 선택한 최종 ADB endpoint 확인 뒤 scrcpy 무실행 검사
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" doctor
```

`wireless-prepare`는 프로필에서 opt-in한 기존 페어링 재연결 한 번만 수행합니다. 이미
정확한 기기가 연결되어 있으면 재연결하지 않습니다. ADB 자체가 페어링된 mDNS 서비스를
먼저 연결한 경우에도 시리얼·모델·부팅 ID를 다시 읽어 검증합니다. 그렇지 않으면 Mac의
`adb mdns services`에서
등록 시리얼의 `_adb-tls-connect._tcp` 포트 하나만 받아 등록된 Galaxy Tailscale 주소로
연결하고 시리얼·모델·현재 부팅 ID를 검증합니다. mDNS가 닿지 않으면 포트를 추측하거나
검색하지 않습니다. 현재 Shizuku 실행기 출력에 이번 시작 작업의
`Starting with wireless adb in port PORT...`가 이미 보이면 그 포트를 먼저 사용합니다.
그렇지 않고 OpenMinis가 정상이면 Wi-Fi와 Android 무선 디버깅 화면을 읽기 전용으로
확인해 현재 연결 포트를 사용하며, 두 경로가 모두 없을 때만 사용자에게 요청합니다.
`wireless-connect`는 정확히 `--port CURRENT_CONNECTION_PORT`만 받으며 `--approved`를
붙이지 않습니다. Shizuku가 이미 `READY`라면 포트를 다시 보려고 Start를 누르지 않습니다.

`steady_adb_enabled=true`인 프로필은 동적 연결을 부트스트랩으로만 사용합니다. 검증된 동적
포트에서 정확한 고정 프로필로 `5555`를 활성화하고, 등록된 Tailscale `:5555` endpoint로
다시 연결한 뒤 ADB doctor가 통과해야 최종 준비 상태입니다. 설정이 꺼진 프로필만 검증된
동적 endpoint를 최종 상태로 사용합니다.
고정 연결 뒤 기존 동적 endpoint가 `offline`으로 남으면 그 포트만
`wireless-disconnect --port CURRENT_CONNECTION_PORT`로 제거하고, fixed `connect`와 ADB
doctor를 다시 실행합니다. 목록에 있다는 사실만으로 `offline` endpoint를 연결 상태로
판정하지 않습니다.
최종 목표가 ADB 또는 scrcpy뿐이면 Shizuku는 부트스트랩 지원이며 완료 조건이 아닙니다.

scrcpy doctor는 프로세스나 창을 시작하지 않습니다. `preflight_ready: true`는 ADB 대상,
scrcpy 설치와 안전 옵션 호환성만 뜻하며 실제 시작 여부는 `launch_verified: false`입니다.
ADB 복구 실패는 ADB·scrcpy 기능만 제한하고 정상인 OpenMinis UI 제어는 계속 사용할 수
있습니다. 같은 세션의 후속 작업은 필요한 경로만 선택적으로 다시 검사합니다.

개인화 설치 파일에는 두 Tailscale 주소가 들어 있으므로 GitHub, 메신저, 공개 이슈에 올리지
않고 대상 Galaxy의 Minis에만 전달합니다. 토큰은 Galaxy에서 설치할 때 새로 생성되며 출력되지
않습니다. 자세한 실패 처리와 원복은
[OpenMinis 브리지 배포 안내](skill/galaxy-control/references/openminis-bridge-distribution.md)를
따릅니다.

## One UI 앱 서랍·폴더 작업

One UI의 폴더 선택기 한 곳만 읽으면 전체 앱 목록이 아닐 수 있습니다. 현재 폴더에 이미 든
앱이 그 선택기에서 숨겨질 수 있기 때문입니다. 이 릴리스는 Galaxy를 조작하지 않고 저장된
자료만 검사하는 두 가지 로컬 검증기를 제공합니다. `replay`와 `union`은 사용자가 지정한
새 Mac 출력 디렉터리만 만들며, `check`는 입력 TSV만 읽습니다. Mac 파일도 쓰면 안 되는
요청에서는 `replay`와 `union`을 실행하지 않습니다.

```sh
# 저장된 ui-dump JSONL을 읽어 한 선택기의 겹치는 구간을 재생
uv run "$GALAXY_SKILL_ROOT/scripts/oneui_inventory.py" replay \
  --input /ABSOLUTE/picker-a.jsonl \
  --output /ABSOLUTE/NEW/picker-a-replay \
  --capture-session CAPTURE_ID \
  --source FOLDER_A

# 같은 시점에 수집한 서로 다른 선택기 둘 이상을 합집합으로 검증
uv run "$GALAXY_SKILL_ROOT/scripts/oneui_inventory.py" union \
  --input /ABSOLUTE/NEW/picker-a-replay/app_selector_inventory.tsv \
  --input /ABSOLUTE/NEW/picker-b-replay/app_selector_inventory.tsv \
  --output /ABSOLUTE/NEW/inventory-union

# 명세·선택 원장·진행 로그·화면의 선택 수를 함께 검증
uv run "$GALAXY_SKILL_ROOT/scripts/oneui_ledger.py" check \
  --manifest /ABSOLUTE/manifest.tsv \
  --ledger /ABSOLUTE/selection-ledger.tsv \
  --progress /ABSOLUTE/progress.tsv \
  --selected-count N
```

핵심 규칙은 간단합니다.

- `N개 선택됨`은 수량만 증명하고, 어떤 앱인지 증명하지 않습니다.
- 선택 원장이 명세와 같고, 원장 행 수가 선택 수와 같아야 합니다.
- 이동 성공은 `목표에 있음 + 소스에서 사라짐 + 예상 개수 일치`로 확인합니다.
- 결과가 애매한 `완료`나 이동은 반복하지 않고 관찰 경로만 바꿉니다.
- 홈 제스처가 알림창을 열면 HOME으로 돌아가 새 상태를 읽고 반대 방향을 한 번만 시도합니다.
- 앱 이동 뒤 페이지·좌표·폴더 위치는 다시 읽습니다.
- 동명 앱 하나만 골라야 한다면 좌표가 아니라 패키지·컴포넌트 증거가 필요합니다.

자세한 안전 가드는 [One UI launcher](skill/galaxy-control/references/oneui-launcher.md),
[folder picker](skill/galaxy-control/references/oneui-folder-picker.md),
[verification](skill/galaxy-control/references/verification.md)에 있습니다. 특정 세션의 앱 수,
폴더 이름, 앱 분류, 좌표, 스크롤 거리는 배포 자료에 넣지 않습니다.

## 주요 인터페이스

```sh
# OpenMinis
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" health
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" ui-info

# 사용자별 OpenMinis Control v2 브리지 패키지
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" doctor

# scrcpy
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" view
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" control
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" stop

# ADB 상태와 공식 Wireless Debugging
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" status
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-status
```

위 One UI 절의 검사기도 임의 옵션을 받지 않는 고정 프로필입니다. 페어링, `adb tcpip`,
네트워크·권한 변경, 재부팅, 전송·결제·삭제는 별도의 명시적 승인이 필요합니다.

## 배포 완성도

- 자동 테스트와 정적·프라이버시 검사 및 일반화 브리지 패키지 검증을 통과한 릴리스:
  `PACKAGE_READY`
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
