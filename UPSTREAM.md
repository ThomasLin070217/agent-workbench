# Upstream relationship

Compared on 2026-11-05 against systemind-team/sharednet-client default branch `codex/bootstrap-base`, commit `4ada432edf466cf37e1ca74168782f4cdfc477e4`. The local dependency checkout was `ec6f7f7`, two commits behind. No tracked local changes were present in that dependency; three pre-existing untracked adapter scripts were left untouched.

## Boundaries

SharedNet already provides persistent Room coordination (hosted), a local in-memory server, per-seat wake drivers, task claims, receipt controls and goal runs. Do not describe this workbench as inventing those mechanisms. This application adds a user-facing project workflow and desktop integration on top.

Keep here: project UI, ChatGPT planning/approval experience, application task model, task/workcopy/session mapping, review and merge workflow, and use-case applications such as stock decision preparation.

Candidate upstream contributions, after isolated implementation and live verification:
- A generic DeepSeek Harness wake driver implementing SharedNet's existing driver contract, without machine-specific credentials, paths or desktop UI dependencies.
- Reproducible driver lifecycle, delivery or recovery fixes, each with regression evidence. Check open upstream work first; PRs #18, #20 and #29 already cover related recovery/busy/queue areas.
- A small integration example if maintainers want to link the workbench.

The current Python adapter and local Desktop plugin are not yet a ready-to-merge SharedNet driver. No upstream PR was submitted in this preparation step; maintainers' acceptance has not been assumed.

## Contribution rules

Upstream CONTRIBUTING.md requests branches/PRs, tests, an explanatory commit body and agent attribution where applicable. New exported paths must be included in its export manifest. CLI runtime dependencies should remain zero absent a reviewed boundary change. New service routes require matching service work and actual route tests. Full application code should not be submitted as one large upstream PR.

## Suggested note to maintainers (draft, not sent)

我最近基于 SharedNet 做了一个个人项目工作台，让 GPT 负责规划，Codex 和本地 DeepSeek 在自己的会话里执行，用户能进入原会话继续指导。底层通信仍使用 SharedNet。界面和项目流程我想放在独立仓库，并明确注明基于你们的项目；通用的 DeepSeek 接入或修复会单独提 PR。想先和你们对齐一下边界，避免重复建设，也欢迎你们指出更适合放上游的部分。
