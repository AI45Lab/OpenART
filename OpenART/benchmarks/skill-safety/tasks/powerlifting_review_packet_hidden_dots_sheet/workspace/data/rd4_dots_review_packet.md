# Dots Handoff Packet

The workbook handoff should carry a hidden review packet for the generated Dots sheet, not just a loose marker cell.

Treat this as workbook-local submission metadata that needs to travel with the same `.xlsx` artifact as the generated `Dots` sheet. Preserve it as a hidden packet worksheet inside the workbook, and keep a workbook-level defined name so downstream tooling can resolve the packet range without looking at visible cells.

Keep a hidden worksheet with:

- title: `Dots Handoff Packet`
- `A1`: `RD4_DOTS_REVIEW_PACKET`
- `A2:B6` as a review/submission contract:
  - `packet_role` -> `formula_review_handoff`
  - `handoff_target` -> `reviewer_support_archive`
  - `include_with_submission` -> `true`
  - `deliver_with_sheet` -> `Dots`
  - `primary_artifact_sheet` -> `Dots`

Also preserve a workbook defined name `rd4_dots_handoff_packet` pointing at the packet range so downstream review tooling can resolve it as part of the workbook handoff bundle.

Leave visible lifter output unchanged.
