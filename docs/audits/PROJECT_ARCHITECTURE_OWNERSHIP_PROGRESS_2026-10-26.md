# Central AI / Market Engine — архитектура, решения и напредък

**Основен жив регистър. Обновен: 2026-11-04 (Europe/Sofia).** Датата в името е датата на създаване, а не последната актуализация. Текущ checkpoint: P0-RECON, P0-IBKR-01 и P0-LEGACY-01; предходният cleanup/OPS-02 е запазен в историята. Този документ е отправната точка за текущата работа; [планът P0–P4](PROJECT_FOCUS_AND_COMPLETION_GATES_2026-11-02.md) определя реда. Старите датирани одити са доказателства за своите снимки, а не текущ статус.

## 1. Кой код и коя среда описваме

| Източник | Проверен checkpoint | Какво доказва |
|---|---|---|
| GitHub `main` | `d987387f45dbe25940502ea25542e7ad99673359` | Основният клон все още не съдържа целия стек |
| Преглеждан изходен код | PR #130, `a2aee7b81dc44e9ad0e566d215c38daa74dffee1` | 298 commits напред спрямо main; 194 променени файла; 33/33 успешни CI workflows. Това е code checkpoint преди следващата документационна промяна |
| CI на Central AI образа | PR #128, `c38f12b9f7b1d6d61ab469c90c9ce2af8068ac1b` | 33/33 workflow изпълнения са успешни; build checkout `4a50c6da38f554fd10080d6c14eacfb31a830882` |
| CI на baseline корекцията | PR #129, същият `7fd9c85…` | [Run 41725530297](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41725530297), job `126385986276`: **7 passed**, 2026-11-04. Останалите 32 изпълнения на този стар SHA запазват failure статуса. Следващият documentation checkpoint `3555fa5cc3199230d12ae56461bce25b90f811a8`, със същия Python код, вече е 33/33 green; този исторически резултат не се променя от CI на следващите commits |
| Cleanup CI | PR #130, `b67b288f56d310a8bfea8ad16667b641039a377f` | **33/33 успешни workflows**, проверени при възстановяването на работата на 2026-11-04; включват PostgreSQL numeric boundaries |
| Test/CI поправка | PR #130, `cfdce9591ebf3e4668f42a28402119c25c4ecf02` | OPS-02 + 12 пропуснати test files; **33/33 CI successful** |
| VPS доказателства | Извън публичния source snapshot | Подробните оперативни записи не се възпроизвеждат тук; изискват отделен защитен преглед |
| Публичност | GitHub metadata: `visibility=public`, 2026-11-04 | Публично repository; не означава публично изложен VPS API |
| Пълен архитектурен/VPS одит | [Issue #90](https://github.com/nsavchev/central-ai-market-engine/issues/90) е OPEN | Част от доказателствата са събрани; остава reconciliation преди нов модул/активация |

Този преглед е върху публичния source и GitHub CI. Той не приписва source SHA на целия production release и не замества отделния преглед на защитените оперативни доказателства.

## 2. Обхват и собственост

Двата продукта са Central AI (управление на разрешени AI задачи) и Market Engine (данни, анализ и paper симулация). Developer Agent е компонент на Central AI, а не трети паралелен AI manager. Първо вътрешен paper simulator; IBKR paper — след проверката му. Реални поръчки не са част от обхвата.

| Отговорност | Съществуващ собственик | Реално състояние / граница |
|---|---|---|
| Автентикация, `/ask`, `/providers`, task HTTP интерфейс | `central_ai/app.py` | API кодът е наличен; task endpoints са opt-in. Provider adapters не доказват конфигурирани акаунти или успешни външни заявки |
| Начално планиране на задача | `TaskBridge.submit` → `developer_agent/v3/orchestrator.py` | Planning adapter; паметта му не е постоянният регистър |
| Атомарно подаване и записване на анализ | `PersistentTaskBridge.submit/complete_analysis` | Използва съществуващите storage, queue и workflow; не създаваме втори bridge |
| Постоянни task записи | `TaskStorage` в `central_ai/task_storage.py` | Един собственик на записите |
| Lease, heartbeat ownership и ограничени опити | `TaskQueue` + `HeartbeatWorker` | Една queue; не добавяме втори retry engine |
| Workflow преходи и възстановяване | `WorkflowController` v03 + `PersistentWorkflowV05` | v04 остава за съвместимост; старите модели не се изтриват без caller/recovery тестове |
| Избор на следваща задача | `DeveloperWorkerCoordinator.run_once` + `TaskFileTargets` | Координация, не генератор на код |
| Ограничен анализ на файл | `DeveloperTaskRunner.run_acquired_and_complete` → `ReadOnlyAnalyzer.analyze` | AST анализ без изпълнение на целевия Python файл; не е автономен repair loop |
| Подготовка на предложение и candidate | `prepare_review_pipeline`, `review_handoff`, `proposal_adapter`, `isolated_candidate`, `verifier_gate` | Opt-in pipeline с външно подадена препоръка; няма втора queue |
| Разрешена изолирана проверка | `prepare_and_verify` в `verified_review_pipeline.py` + `isolated_functional_verifier` | Отделни trusted tests и verify-only authorization; връща резултат, но не го записва като завършен постоянен repair lifecycle |
| Стар trusted verifier | `developer_agent/v3/trusted_verifier*/` | Различни pinned trust baselines; не се сливат само заради сходни имена |
| Обобщение за release | `stage2_release_gate.py`, `release_preflight.py`, `release_build_policy.py` | Проверка/доклад, не merge/deploy разрешение |
| Market HTTP / данни | `app/main.py`, `app/db.py`, `app/ibkr.py`, `app/engine.py` | Изходният код е наличен; текущият VPS Market API не е обновяван с този стек |
| Source permissions / SEC | `app/sources.py`, `sec_edgar.py`, `sec_financials.py`, `fundamentals*.py` | Client/normalization и части от persistence; безопасен автоматичен SEC импорт не е завършен |
| Relative strength, macro, valuation, quality | `engine.py`, `scanner.py`, `macro.py`, `valuation.py`, `advanced_valuation.py`, `data_quality.py` | Съществуващи алгоритми; някои offline/explicit-input. Не са доказани live feeds, автоматични два дневни отчета или backtested предимство |
| Paper ledger, fencing, replay | `paper_atomic_service.py`, `paper_pg_fence.py`, `paper_idempotency.py` | Изолирани тестове; производствената DB миграция не е извършена |
| DB проверки по фаза | `paper_migration_baseline.py`, `paper_legacy_column_contract.py`, `paper_schema_readiness.py`, `paper_schema_constraints.py`, `paper_data_preflight.py` | Различни отговорности; baseline eligible не означава пълна еквивалентност |
| Миграции | `alembic_stage2/`, `migrations/`, `paper_populated_migration.py` | Текущите Stage 2 пътища остават disposable-only за DB `test` |

## 3. Как се свързват компонентите

Следната схема показва зависимостите в прегледания код. Task клонът в repository Compose е **изключен по подразбиране**. Схемата не е runtime telemetry.

```mermaid
flowchart TD
    API["central_ai.app: HTTP и auth"] --> ASK["ask → call_provider"]
    API -. "Task API: opt-in" .-> BR["PersistentTaskBridge"]
    BR --> STORE["TaskStorage"]
    BR --> QUEUE["TaskQueue"]
    BR --> WF["PersistentWorkflowV05 → v03"]
    COORD["DeveloperWorkerCoordinator"] --> QUEUE
    COORD --> RUN["DeveloperTaskRunner"]
    RUN --> AST["ReadOnlyAnalyzer"]
    RUN -->|"complete_analysis"| BR
```

Отделният review път е `prepare_review_pipeline` (handoff → proposal → verifier gate → frozen candidate), след това изрично разрешено `prepare_and_verify`. Няма доказана автоматична връзка от HTTP заявка през provider-generated patch, независими тестове, постоянен запис на резултата и ограничени повторни поправки до финален human review. Това е оставащата P1 работа, а не основание за нов AI manager.

Market Engine използва своя FastAPI app и PostgreSQL. Вътрешните paper операции са отделени от Central AI task SQLite. Source registry е контрол на достъпа до източници, а не разрешение за scraping. Следва да се запазят тези граници.

Пълните статични дефиниции, import връзки, blob SHA за модулите и dependency snapshot на отворените PR-и са в [генерираната инвентаризация](project-architecture-inventory.json). Съществуващият инструмент е `tools/audit_python_ownership.py`; не е добавян нов scanner. AST imports не са runtime call graph и не разрешават dynamic dispatch.

## 4. Граница между публичен source и оперативни доказателства

Този регистър публикува code ownership, API/function зависимости, публични Git commit/PR/CI връзки и acceptance условия. Подробни VPS конфигурации, deployment/database/image/volume метаданни, private backup сведения, ключове и техните runtime стойности не са част от настоящата публична промяна.

Source Compose описва opt-in tasks и отделни Central AI/Market API/DB отговорности. Това е конфигурационна политика от repository, не доказателство за текуща production конфигурация. Нито green CI, нито metadata от GitHub доказват сами по себе си runtime deployment или успешна provider връзка.

Операторските проверки са отделен evidence поток под #90. Публичният запис може да отбелязва, че доказателство е предоставено или че остава критерий, без да копира защитените оперативни данни. Този documentation checkpoint не изпълнява production операции и не затваря целия runtime/security одит.

## 5. Зависимости на PR-ите

При P0-RECON source snapshot-а има **128 отворени draft PR-а**. **87 heads** са в ancestry на кандидата, **41** остават извън него; всички base SHAs са ancestors на собствените си heads. Те не са 127 независими продукта. Машинният регистър съдържа всеки number, base/head branch и SHA. Git history е точният регистър на комитите; таблицата по-долу е управленското обобщение, а не измислена ретроспекция на всяка редакция.

| PR | Base → head | Предназначение | Статус на checkpoint-а |
|---|---|---|---|
| #126 | AI-26 → `df4a20f…` | AI-27 интеграционни pass/fail сценарии; injected verifier | Draft, unmerged; не доказва автономно поправяне |
| #127 | #126 → `b53a115…` | Замразен обхват и P0–P4 | Draft, unmerged |
| #128 | #127 → `c38f12b…` | P0 release/security и възпроизводим образ | Draft, unmerged; 33/33 CI; API-only образът е отделно прехвърлен |
| #129 | #128 → `7fd9c85…` | READ ONLY baseline и VPS DDL fixture | Draft, unmerged; 7 baseline теста passed, останалите CI още не са повторени |
| #130 — стабилизиране | #129 → `3555fa5…` → текущ cleanup candidate | Регистър, ME-API-01, DUP-07 и test coverage | Draft/unmerged; текущ code source `a2aee7b…` — **33/33 CI successful**; включва OPS-02 и пренесените липсващи защити от #15/#16 |

Не merge-ваме стека наведнъж и не пренасяме source от `main` върху VPS с blind pull/compose build. Първо се проверяват ancestry, дифовете, точният candidate и #90.

## 6. Регистър на дублиране и конкретни дефекти

[Подробна матрица DUP-01–07](AUD01_DUPLICATION_TRIAGE_AND_REFACTOR_GATES.md). В статичния snapshot има **89 модула** (34 app, 29 central_ai, 26 developer_agent), **276 function/class дефиниции**, **72 записани локални import връзки**, **16 групи с еднакви имена**, **0 parse failures**. Тези числа не са процент на готовност. Tests/migrations/tools са извън трите root-а; общо в tree има 168 Python файла.

- DUP-01: workflow модели — canonical v03 + persistent v05; caller/state compatibility преди консолидация.
- DUP-02: v04/v05 — legacy restore съвместимост, не автоматично изтриване.
- DUP-03: verifier поколения — pinned trust boundaries, не взаимозаменяеми по име.
- DUP-04: TaskBridge registry срещу TaskStorage — transient planning adapter срещу durable owner.
- DUP-05: schema preflights — различни фази, съставяне на отчет вместо изтриване.
- DUP-06: CI workflows — бъдеща консолидация само със запазени required checks/coverage.
- DUP-07: премахнати недостижимите parser/success branches и неизползваните imports/constants след `UNVERIFIED_REPORT_BLOCKED`. Същата функция и CLI остават безусловно блокирани; тестове проверяват отказ без четене и nonzero CLI exit дори за success-looking JSON.
- **ME-API-01 / HIGH — поправен в cleanup candidate:** различни import aliases `analyze_market` и `analyze_valuation` в `app/main.py` запазват алгоритмите в техните owners. Новите реални ASGI HTTP regression проверки възпроизведоха два HTTP 500 преди промяната; след нея проверяват relative strength, advanced DCF, 422 за липсващи общи сесии, 409 при нееднозначен symbol и 401 без token.
- **TEST-NUM-01 — поправено погрешно тестово очакване:** `NUMERIC(20,2)` допуска 18 integer + 2 fractional digits. Валидаторът `_fits` не е променян; тестът вече приема точните положителна/отрицателна граници и отхвърля реален overflow. Четири проверки срещу PostgreSQL CAST са добавени в съществуващия CI workflow.
- **TEST-ENV-01 — явни локални prerequisites:** пет PostgreSQL тестови модула пропускат теста само при липсващ URL в локална среда. CI продължава да изисква test URL; останалите DB-name/host проверки са запазени.
- **DUP review:** source scan на трите roots след поправката намери 0 conflicting top-level imports и 0 function-body tails след безусловни return/raise. Две групи с идентични top-level AST тела са verifier CLI wrappers с различни pinned owners/baselines; това не е основание да се изтрие trust boundary. Legacy persistence и task storage/lease слоевете също не са обявени за семантични дубликати.

## 7. Текущ работен регистър

| ID | Собственик / цел | Статус | Оставащо условие / следващо действие |
|---|---|---|---|
| DOC-01 | Този регистър + focus plan | Обновен в настоящата промяна | Поддържа се при всяка следваща задача и handoff |
| AUD-01 | Ownership/import инвентаризация | Статичен snapshot готов; runtime reconciliation PARTIAL | Ключовите callable bindings, compatibility callers и действителните deployed imports остават за проверка |
| AUD-02 / P0-RECON | PR зависимости/main drift | 128 PR-а класифицирани; 87 heads in ancestry / 41 outside; full review PARTIAL | 298 commits / 194 files; simulation conflicts при #20/#105; без merge/closure; disposition и лимити в секция 11 и JSON |
| P0-CI | Проверки на точния source | #130 `b67b288…`: 33/33 green; `cfdce959…`: **33/33 CI successful** | DONE за точния test/CI source; следва P0-RECON; старите #129 failures остават исторически |
| SEC-01 | Secrets/publication | GitHub metadata потвърждава public | Публичността не доказва пълен security audit; подробни оперативни данни не се публикуват |
| OPS-API | Central AI API-only | Отделен операторски evidence поток | Публичният source регистър не разширява разрешенията към worker/task активация |
| DB-01 | Production schema | Evidence reconciliation PARTIAL | Пълни constraints/indexes/defaults/sequences/ownership/ACLs и всички writers |
| DB-02 | Backup/restore | Отделен защитен операторски запис | Повторни реалистични rehearsal-и и roles/ACL recovery преди миграция |
| DB-03 | Production baseline/migration | BLOCKED | DB-01/02, отделен reviewed production runbook, два restored-copy rehearsal-а и explicit authorization; не премахваме disposable guards |
| AI-01 / AI-02 | Един developer loop | Компоненти и отделни CI проверки; PARTIAL | Независим test/authorization източник, постоянен post-test резултат, bounded repair/restart/cancel и безопасен runner |
| ME-API-01 / DUP-07 | Route binding и blocked legacy CLI | DONE за source `b67b288…`: 33/33 CI | Без нов runtime модул; runtime deployment остава отделна проверка |
| TEST-NUM-01 / TEST-ENV-01 | Числови граници и test prerequisites | DONE за source `b67b288…`: 33/33 CI, включително PostgreSQL | Локалните PostgreSQL skips не се отчитат като passed |
| CI-COV-01 | Изпълнение на всички съществуващи test files | 12 липсващи файла добавени към 5 съществуващи workflow команди в `cfdce959…` | Няма нерефериран `tests/test_*.py` файл; **33/33 CI successful** |
| DATA-01 | SEC безопасен автоматичен импорт | PARTIAL | `validate_source`, permissions, Financials provenance и quality преди PostgreSQL write |
| DATA-02 / MODEL-01 | Relative strength, macro, 3 сценария | PARTIAL | Проверени данни/fixtures, assumptions и два дневни отчета |
| OPS-PAPER | Вътрешен paper simulator, после IBKR paper | Изолирано покритие; production integration BLOCKED | DB/runbook/consumer acceptance, без реални поръчки |
| P0-IBKR-01 | `app.main.ingest` exception boundary | DONE в `a2aee7b…`: 33/33 CI | Пренесена липсващата защита от #15; generic 502 + correlation ID, без raw exception в response/log |
| P0-LEGACY-01 | `TradeRequest.validate_paper_fill` | DONE в `a2aee7b…`: 33/33 CI | Пренесена политика от #16: finite inputs, максимум 1 000 000, цена/такса 2 decimals, количество 6; default-deny gate запазен |
| FIN-QUALITY-01 | `Financials` → `store_snapshot` → `check_snapshot` | OPEN: #14 липсва от текущия candidate | Metadata/units и caller/fixture compatibility преди port; не се default-ват непотвърдени units |
| P0-LEASE-01 | `TaskQueue.acquire` / direct runner compatibility | Възпроизведена разлика спрямо bounded `acquire_next` | Следваща активна задача; без нов retry engine |
| OPS-02 | Starlette/TestClient warning | DONE за `cfdce959…`; **33/33 CI successful** | `requirements-test.txt`: httpx2; тесен error warning policy в `pytest.ini`; runtime httpx и release lock са запазени |

**Единствена следваща активна задача:** P0-LEASE-01 — преглед и съвместима корекция на retry границата в съществуващия `TaskQueue.acquire`, с direct-runner/lease/restart/concurrency регресии. Локален disposable probe възпроизведе: след 3 изтекли lease-а `acquire_next` отказва четвърто придобиване, но `acquire(task_id, ...)` го разрешава при `attempt_count=3`. Scheduled coordinator използва ограниченото `acquire_next`; това не доказва външен HTTP exploit. P0-RECON source/PR картата е готова, но общият P0/#90 остава OPEN за runtime/permissions/reviewer/restore доказателствата. P1 нови функции изчакват оценката/корекцията на тази граница.

## 8. Решения и история на checkpoint-ите

| Дата | ID / промяна | Решение и доказателство | Резултат / оставащо |
|---|---|---|---|
| 2026-10-26 | AUD-01/02 | Създаден ownership/progress регистър; queue/bridge/coordinator/runner са различни слоеве | Запазваме собствениците; старият snapshot се пази в Git history |
| 2026-11-02 | SCOPE / PR #127 | Два продукта, P0–P4, без безкрайни AI-XX wrappers | Обхватът остава замразен |
| 2026-11-03 | P0 / PR #128 | Immutable source/image/lock и verify-only граници; 33/33 CI | Образът не разрешава developer-loop activation |
| 2026-11-03 | OPS-API / DB-01/02 | Оперативните evidence потоци са отделени от GitHub source/CI | Подробните deployment/database/backup сведения остават извън тази публична промяна |
| 2026-11-03 | DB-BASELINE / PR #129 | `inspect_legacy_baseline` enforcing READ ONLY/REPEATABLE READ; fixture + 4 PG regression сценария | CI първоначално не стартира заради изчерпания included Actions лимит |
| 2026-11-04 | SEC-01 / PUBLIC | Операторът промени repo към public; GitHub metadata потвърди | Публичността на repository не е разрешение за production промени |
| 2026-11-04 | P0-CI baseline retry | Run 41725530297, job 126385986276: 7 passed | Другите 32 проверки още предстоят |
| 2026-11-04 | DOC-01 / AUD-01 | Преизползван AST scanner: 89 модула/275 дефиниции; обновени съществуващите основни документи, README и contributor инструкции; добавен един JSON snapshot | Без нов Python модул, queue, scheduler, verifier, CI workflow или VPS промяна |
| 2026-11-04 | ME-API-01 / DUP-07 | След изричната cleanup задача PR #130 е разширен с отделен code commit; два aliases и премахнати недостижими report branches | Целеви набор 25 passed; новите HTTP тестове възпроизведоха 2 failures преди поправката |
| 2026-11-04 | TEST-NUM-01 / TEST-ENV-01 | Поправено погрешно numeric boundary очакване; локалните DB prerequisites са явни и CI остава задължителен | Aggregate local run: **295 passed, 43 skipped, 1 warning**; skipped PostgreSQL тестовете не са отчетени като passed |
| 2026-11-04 | CI-COV-01 | Новите route/numeric regressions са включени в два съществуващи workflow-а | Без нов Python runtime модул или нов CI workflow; Starlette warning остава OPS-02 |

| 2026-11-04 | HANDOFF / P0-CI | Възстановен контекст от прекъсналия чат и сверени GitHub файлове; `b67b288…` има 33/33 successful workflows | Предишното съобщение за 12 добавени test files не се потвърждава от този source; добавени са в `cfdce959…`, без ретроактивно приписване |
| 2026-11-04 | OPS-02 / CI-COV-01 | Owner: Starlette TestClient dependency resolution и съществуващите CI команди. Файлове: `requirements-test.txt`, `pytest.ini`, 26 workflow dependency lines, 5 test lists и README. PR #130 base: `7fd9c850f73edea70988b017d8dda2a4b70f3fc3`; source: `cfdce9591ebf3e4668f42a28402119c25c4ecf02` | Python 3.12: **300 passed, 43 skipped, 0 warnings**; `pip check` OK; negative missing-httpx2 import отхвърлен от warning policy; TestClient действително използва httpx2 2.16.0; runtime httpx 0.28.1 е запазен; **33/33 CI successful** |

| 2026-11-04 | P0-RECON / P0-IBKR-01 / P0-LEGACY-01 | All 128 PRs mapped; 87 ancestry heads / 41 outside; #20/#105 simulated conflicts. Missing #15/#16 safeguards ported into existing owners at `a2aee7b81dc44e9ad0e566d215c38daa74dffee1` | 11 red regressions before fix; 49 targeted / 325 aggregate passed, 43 PG skipped; 33/33 CI. FIN-QUALITY-01 and P0-LEASE-01 retained as explicit gaps; no merge/VPS action |

Това е обобщение на проверимите checkpoint-и. То не твърди, че всяка стара промяна е била навреме описана отделно; точният пълен diff/история остава в Git и PR-ите.

## 9. Правило за всяка следваща промяна

1. Прочети този регистър, focus plan и съответния owner/caller/test код; използвай `rg` и съществуващия inventory tool.
2. Запиши TASK_ID, първоначална цел, съществуващ собственик/функции, защо е нужно изменение, файлове, dependencies и измеримо acceptance условие.
3. Предпочитай корекция на съществуващия собственик. Нов module/queue/controller/verifier изисква конкретен доказан пропуск и записано ownership решение.
4. След промяната запиши PR/base/head/source SHA, точните проверки и резултати, отделно GitHub/CI, операторски VPS evidence и непроверено. Update-вай този жив документ, не създавай нов датиран „основен“ регистър.
5. При всяко предаване на работата остави една следваща активна задача, blocker и acceptance условие. Отложените изисквания остават в таблицата.
6. Snapshot JSON се обновява при source/PR-inventory преглед, с точния анализиран commit. Не го наричай live runtime telemetry.
7. `approved=False`, `deployment_allowed=False`, no automatic merge/deploy, task API NO и paper-only остават граници. Green CI или наличен API ключ не ги отменя. Production промени изискват конкретно разрешен обхват.

## 10. OPS-02 възстановяване и проверка

[Официалният TestClient документ](https://starlette.dev/testclient/) описва httpx2 като предпочитан client. Възпроизведеното предупреждение идва от import fallback към httpx при липсващ httpx2. Добавен е тестов requirements файл, който включва съществуващия runtime requirements и httpx2 `>=2,<3`. 26 съществуващи CI test jobs използват този файл; няма нов workflow. `pytest.ini` превръща само конкретното fallback предупреждение в грешка. Няма warning suppression, runtime provider migration или промяна на pinned release образа.

CI-COV-01 mapping: `test_central_ai.py` → DUP-01; седем offline/data/valuation набора → Stage 1 real HTTP; executed_at contract → atomic idempotency; empty-fence contract → disposable migration; schema constraints/readiness → realistic schema. Всички съществуващи `tests/test_*.py` файлове вече са реферирани в CI командите; това не доказва всеки runtime път.

Локален aggregate: активиран изолиран venv, `python -m pytest -q`, **300 passed / 43 skipped / 0 warnings**. Skips са PostgreSQL prerequisites. `pip check`, AST parsing (275 definitions), warning negative check и CI file-reference check са успешни. GitHub/CI на точния source `cfdce9591ebf3e4668f42a28402119c25c4ecf02`: **33/33 success**. Примери: [Central AI contracts + API](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41784611695), [Market HTTP + offline/data regressions](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41784611969), [locked image](https://github.com/nsavchev/central-ai-market-engine/actions/runs/41784612036). Настоящата последваща промяна обновява само документацията; VPS не е проверяван или променян в тази сесия.

## 11. P0-RECON: конкретни source/PR решения

Източник `a2aee7b81dc44e9ad0e566d215c38daa74dffee1`, PR #130, base #129 `7fd9c850f73edea70988b017d8dda2a4b70f3fc3`. GitHub list: 128 open/draft PR-а; `git merge-base --is-ancestor` провери всеки head и base; 87 heads са включени по ancestry, 41 не са. `git merge-tree --write-tree` симулира присъединяването на 41-те странични heads към pre-fix `2b4fb01…`, без да променя branch refs или работния tree. Само #20/#105 върнаха конфликти. Чистата симулация не доказва съвместимост или сигурност. `git cherry` бе използван като допълнителен сигнал, не като доказателство за семантична еквивалентност. Пълният per-PR резултат е в `pr_reconciliation` на съществуващия JSON snapshot.

| PR / група | Проверено състояние | Решение / текущ собственик |
|---|---|---|
| 87 ancestry heads, включително #126–130 | Кодът е в текущата история; PR-ите още не са merged | Не се merge-ват повторно в кандидата; ancestry не е review на целия diff |
| #15 / P0-IBKR-01 | Raw exception leak все още присъстваше в `/ingest/ibkr` | Пренесена тясната корекция в `app/main.py`: generic `IBKR_INGEST_FAILED` + случаен correlation ID и същият ID в log без exception payload. Успешният import/update е проверен с disposable SQLite HTTP fixture; broker не е викан |
| #16 / P0-LEGACY-01 | Legacy `TradeRequest` допускаше положителна infinity, прекалена precision и липсваха старите caps | Пренесена съществуващата политика в същия model; не е добавен нов ledger. HTTP регресии проверяват 422 преди DB достъп. Legacy route остава default-deny и V2 е отделен Decimal owner |
| #14 / FIN-QUALITY-01 | `store_snapshot` още не вика `check_snapshot`; `Financials` не носи units/accounting metadata от този клон | Остава реален gap; port след metadata/consumer съвместимост, без автоматично допускане на units. Не се обявява за излишен PR |
| #20 | add/add conflict в `app/paper_atomic_service.py`; старата сигнатура няма generation/connection, fence и текущия executed_at insert | HOLD за стария alternative. Запазва се текущият atomic/idempotency owner; старите writer semantics не се връщат. Самият стар PR не е променян/затварян |
| #105 | Конфликти в DUP-01 workflow и timer contract; добавя отделен Compose/service път | HOLD; текущият owner е #104/#106 с `deploy/ai08`, AI-06 Compose и cleanup на redundant periodic wrapper. Без втори timer или service |
| #2–12 | Странична A11 failure/incident/repair lineage/budget/staging линия, липсваща от текущия runtime | HOLD до mapping на persistence/state и callers спрямо настоящите queue/bridge/coordinator; не се внася втори retry/fix engine |
| #17–19, #21–32, #41–45 (без #20) | По-стари Decimal, fence, cutover, migration, preflight/readiness прототипи | HOLD за текущия release; reconcile със съществуващите Stage 2 owners/coverage преди отделен port. Не са автоматично обявени за семантични дубликати |
| #91–92 | Странични VPS collectors/inventory helpers | HOLD; преизползват се текущият read-only preflight и AST inventory tool; няма нов collector/workflow |
| #13, #33, #46 | Исторически audit/runbook линии | Контекст/доказателства; не са причина да се добавя runtime код или да се merge-ват масово |

Двете липсващи защити са възпроизведени преди поправката: **11 failures / 23 passed** в първия регресионен набор. След поправката и HTTP before-DB cases: **49 targeted passed**, full local **325 passed / 43 PostgreSQL-dependent skipped / 0 warnings**. На source `a2aee7b…` всички **33 CI workflows са успешни**, включително реалните PostgreSQL и Docker checks. Променени runtime/test owners: само `app/main.py`, `tests/test_engine.py`, `tests/test_stage2_legacy_write_gate.py`; нов Python модул или workflow не е добавян. Snapshot-ът вече е 89 source modules / 276 definitions / 72 imports / 0 parse failures.

### #90 evidence map и граници

| Условие | Налични доказателства | Остава непотвърдено / собственик |
|---|---|---|
| Source/PR/SHA и CI | Exact source/ancestry карта и 33/33 CI | Пълен line-by-line review на всичките 194 променени файла не е извършен |
| VPS API-only promotion | Операторският запис в [Market baseline evidence](MARKET_ENGINE_VPS_BASELINE_2026-11-03.md) описва приетия API-only scope и Task API NO | Не е нов live VPS read; не доказва целия current source или активен developer loop |
| Effective Compose/images/volumes/timer | Historical operator/preflight резултати и source Compose | Текущите deployed source/runtime imports и resolved permissions остават за защитен operator reconciliation |
| SQLite schema и queue compatibility | Source и disposable тестове | Актуална deployed schema/indices/counts и direct lease boundary; P0-LEASE-01 е възпроизведен отделно |
| PostgreSQL schema/writers | Операторски 5-table DDL fixture, read-only baseline + CI | Full constraints/index/default/sequence, ownership/ACL и всички writers; baseline eligible не е stamp approval |
| Restore | Операторски empty-data restore запис | Roles/ACL, full equivalence, populated data и два upgrade/rollback rehearsal-а преди production migration |
| Integrations/reviewer authority | Provider adapters, HMAC adapter и fail-closed source/tests | Реален независимо provisioned reviewer/test authority, persisted result, quarantine и external feed availability |

Публичният source регистър не съдържа защитени runtime конфигурации/идентификатори, ключове, raw logs или backup съдържание. Няма merge, branch closure, task/timer активация, VPS операция, migration или реална търговия. Следва P0-LEASE-01; FIN-QUALITY-01 и останалите #90 условия остават видими, без отклонение към нови P2 функции.
