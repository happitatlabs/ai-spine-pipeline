# Spine CLI Export Setup

## 목적

`Spine.com`을 절대경로로 호출해서 `.spine` 프로젝트를 PowerShell에서 자동 export한다.

현재 기준으로 검증한 범위는 다음과 같다.

- `.spine` 입력 파일 지정
- 출력 폴더 자동 생성
- `json+pack` export 수행
- 결과물 `.json`, `.atlas`, `.png` 생성 확인

## 현재 세팅값

- Spine CLI 경로: `C:\Program Files\Spine\Spine.com`
- 작업 루트: `D:\Spine`
- 프로젝트 입력 루트: `D:\Spine\projects`
- export 출력 루트: `D:\Spine\export`
- export 스크립트: [spine_export.ps1](D:\Spine\spine_export.ps1)
- Git 저장소: `D:\Spine\.git`

## 디렉토리 구조

```text
D:\Spine
  README.md
  spine_export.ps1
  projects\
  export\
  vendor\
```

현재 확보한 공식 예제는 아래 경로에 있다.

- 원본 예제 저장소 일부: `D:\Spine\vendor\spine-runtimes`
- 테스트용 복사본: `D:\Spine\projects\spineboy\spineboy-ess.spine`

## Git 기준 운영

현재 `D:\Spine`은 Git 저장소로 초기화되어 있다.

```powershell
git -C "D:\Spine" status
```

기본 추적 대상:

- `README.md`
- `spine_export.ps1`
- `.gitignore`
- 빈 디렉토리 유지용 `.gitkeep`

기본 제외 대상:

- `export/`
- `vendor/`
- `projects/`

이렇게 둔 이유:

- `export/`는 생성 산출물이므로 버전 관리 대상이 아님
- `vendor/`는 공식 예제/외부 소스 복사본이므로 기본 제외
- `projects/`는 실제 작업용 `.spine` 자산이 들어갈 가능성이 높아 기본적으로 로컬 관리

나중에 실제 `.spine` 프로젝트 자체를 Git에 올리고 싶으면 `.gitignore`에서 `projects/` 관련 규칙을 조정하면 된다.

초기 업로드 예시는 아래처럼 진행하면 된다.

```powershell
git -C "D:\Spine" add README.md spine_export.ps1 .gitignore projects/.gitkeep export/.gitkeep
git -C "D:\Spine" commit -m "Add Spine CLI export automation setup"
```

## 기본 사용법

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-ess"
```

기본 export 모드는 `json+pack`이다.

- `json+pack`: `.json`, `.atlas`, `.png`
- `json`: `.json`
- `binary+pack`: `.skel`, `.atlas`, `.png`
- `binary`: `.skel`

모드를 바꾸려면 `-ExportMode`를 명시한다.

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-json-only" `
  -ExportMode "json"
```

## 실제 검증 결과

다음 명령으로 실제 export를 확인했다.

```powershell
& "D:\Spine\spine_export.ps1" `
  -InputPath "D:\Spine\projects\spineboy\spineboy-ess.spine" `
  -OutputPath "D:\Spine\export\spineboy-ess"
```

생성 결과:

```text
D:\Spine\export\spineboy-ess\
  spineboy-ess.json
  spineboy-ess.atlas
  spineboy-ess.png
```

## 알아야 하는 것

### 1. PATH 등록에 의존하지 않는다

`Spine.com`은 PATH에 없으므로 항상 절대경로로 호출한다.

```powershell
& "C:\Program Files\Spine\Spine.com" ...
```

### 2. `-u`는 headless 옵션이 아니다

처음 가정과 달리 `-u`는 `update` 옵션이다. export 실행에는 쓰지 않는다.

- 잘못된 이해: `-u = UI 없이 실행`
- 실제 의미: `-u = 특정 Spine 버전 업데이트/선택`

export에는 보통 아래 조합을 사용한다.

```powershell
& "C:\Program Files\Spine\Spine.com" `
  -i "<input.spine>" `
  -o "<output-folder>" `
  -e "json+pack"
```

### 3. `.atlas`와 `.png`까지 원하면 `json`만으로는 부족하다

`-e json`은 JSON 데이터 export만 의미한다.

`.atlas`와 `.png`까지 같이 만들려면 `-e json+pack`을 사용해야 한다.

### 4. 자동화할 때는 같은 프로젝트를 열어둔 Spine 창을 닫는 쪽이 안전하다

필수는 아니지만 아래 이유로 닫고 실행하는 것을 권장한다.

- 같은 `.spine` 파일을 GUI에서 열어 둔 상태와 충돌 가능성
- 미저장 변경 반영 여부 혼선
- 배치 작업 시 재현성 저하

권장 운영 기준:

- 수동 테스트: 열려 있어도 될 수 있음
- 배치/자동화: 닫고 실행 권장
- 같은 프로젝트 편집 중: 저장 후 닫고 실행 권장

### 5. Spine CLI도 실행 환경 영향을 받는다

이번 검증에서 일반 실행은 성공했지만, 제한된 실행 환경에서는 `Spine.com`이 비정상 종료할 수 있었다.

가능한 원인:

- OpenGL/윈도우 시스템 접근 제한
- 자동화 도구의 샌드박스 제한

따라서 실제 운영 자동화는 일반 PowerShell 또는 충분한 권한이 있는 실행 환경에서 돌리는 것이 안전하다.

### 6. 버전 매칭이 중요하다

Spine editor의 major/minor 버전과 runtime 쪽 major/minor 버전은 맞춰야 한다.

예:

- editor `4.2.x` -> runtime도 `4.2`
- editor `4.3.x` -> runtime도 `4.3`

현재 확인된 실행 버전:

- Launcher: `4.3.02`
- 실행된 Editor: `4.2.43 Professional`

## 문제가 생기면 먼저 볼 것

### 입력 파일 없음

오류 예:

```text
Input .spine file not found: ...
```

확인:

- 경로 오타
- `.spine` 확장자 여부

### export는 끝났는데 결과물 일부가 없음

확인:

- `-ExportMode`가 `json+pack` 또는 `binary+pack`인지
- 출력 폴더를 잘못 보지 않았는지

### Spine 자체가 종료 코드와 함께 죽음

확인:

- Spine 창을 닫고 재시도
- 일반 PowerShell에서 재시도
- `C:\Users\Hyein\Spine\spine.log` 확인

## 다음 확장 후보

- `D:\Spine\projects` 전체 순회 일괄 export
- 프로젝트별 출력 폴더 자동 매핑
- 로그 파일 저장
- CI/빌드 파이프라인 연결
