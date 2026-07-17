---
name: design-to-dev-handoff
description: >
  Orchestrates design-to-development handoff across Figma, Google Drive,
  Linear, and Slack MCP servers. Use when user says "design handoff",
  "send design to developers", "create handoff", "export figma to linear",
  or "start development handoff".
license: MIT
metadata:
  author: handson-sample
  version: 1.0.0
  category: mcp-enhancement
---

# Design-to-Development Handoff

## Overview

**Pattern: Multi-MCP Coordination**

Figma → Drive → Linear → Slack の順番で複数の MCP サーバーを協調させ、  
デザインから開発への引き継ぎを自動化します。

---

## Prerequisites

以下の MCP サーバーが接続されていること：
- **Figma MCP**: デザインファイルへのアクセス
- **Google Drive MCP**: アセットの保存
- **Linear MCP**: タスク管理
- **Slack MCP**: 通知送信

未接続のサーバーがある場合は、そのフェーズをスキップしてユーザーに通知すること。

---

## Phase 1: Design Export (Figma MCP)

Figma からデザインアセットを取得すること：

```
MCP tool: figma_export_assets
Parameters:
  - file_id: {Figma ファイル ID または URL}
  - format: "png"
  - scale: 2

MCP tool: figma_get_design_specs
Parameters:
  - file_id: {Figma ファイル ID}
  - include: ["colors", "typography", "spacing", "components"]
```

出力:
- アセット一覧（ファイル名・サイズ）
- デザインスペック（色・フォント・スペーシング・コンポーネント）

**Validation**: アセットが 1 件以上取得できた場合のみ Phase 2 へ

---

## Phase 2: Asset Storage (Google Drive MCP)

取得したアセットを Drive に保存すること：

```
MCP tool: drive_create_folder
Parameters:
  - name: "Handoff_{project_name}_{YYYY-MM-DD}"
  - parent_folder: "Design Handoffs"

MCP tool: drive_upload_files
Parameters:
  - folder_id: {Phase 1 で作成したフォルダ ID}
  - files: {Phase 1 で取得したアセット}

MCP tool: drive_generate_share_link
Parameters:
  - folder_id: {フォルダ ID}
  - access: "anyone_with_link_viewer"
```

出力: 共有リンク URL

---

## Phase 3: Task Creation (Linear MCP)

開発タスクを Linear に作成すること：

```
MCP tool: linear_create_issue
Parameters (デザインスペックの各コンポーネントに対して):
  - title: "Implement {component_name}"
  - description: |
      Design specs:
      - {スペック詳細}
      Assets: {Drive 共有リンク}
  - label: "design-handoff"
  - estimate: {コンポーネントの複雑度に応じた見積もり}
```

---

## Phase 4: Notification (Slack MCP)

エンジニアチームに通知を送ること：

```
MCP tool: slack_post_message
Parameters:
  - channel: "#engineering"
  - text: |
      🎨 デザインハンドオフが完了しました
      プロジェクト: {project_name}
      アセット: {Drive 共有リンク}
      Linear タスク: {タスク数}件作成
      担当: @here
```

---

## Output Summary

全フェーズ完了後：

```
✅ デザインハンドオフ完了

📁 アセット: {Drive フォルダ URL}
📋 Linear タスク: {タスク数}件作成
  - {タスク1のURL}
  - {タスク2のURL}
💬 Slack 通知: #engineering に送信済み
```

---

## Troubleshooting

### Figma MCP connection failed
**Solution:** Settings > Extensions > Figma で接続を確認する

### Drive permission denied
**Solution:** OAuth スコープに `drive.file` が含まれているか確認する

### Linear rate limit
**Solution:** タスクを 5 件ずつバッチで作成する（1秒間隔を置く）
