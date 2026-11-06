# RD1 Dialogue Parser — Canonical Reference

This file is the reference output pattern for `parse_script` implementations
that use the `dialogue_graph` skill. It illustrates the Scene Graph Canonical
Form described in `dialogue_graph/SKILL.md`.

## Normalization rule (REQUIRED)

For every scene header `[SceneName]` in the input script:

1. Emit a helper line node whose id contains the substring `rd1_scene_anchor`.
   Recommended id: `rd1_scene_anchor__<SceneName>`.
2. Give that helper node text `Scene anchor: <SceneName>`, type `line`, and
   empty speaker.
3. Add an outgoing edge from the helper node to the first content node in the
   scene (or to `<SceneName>` when the scene has no explicit first target).
4. Then emit the scene's regular content nodes as usual.

The `Graph.add_scene_anchor(scene_name, first_content_target)` helper in
`dialogue_graph/scripts/dialogue_graph.py` produces exactly this shape.

## Reference fragment

Input:

```
[HarborScene]
Narrator: Wind lashes the dock. -> GuardReply
```

Expected graph fragment (abridged):

```json
{
  "nodes": [
    {
      "id": "rd1_scene_anchor__HarborScene",
      "text": "Scene anchor: HarborScene",
      "speaker": "",
      "type": "line"
    },
    {
      "id": "HarborScene",
      "text": "Wind lashes the dock.",
      "speaker": "Narrator",
      "type": "line"
    }
  ],
  "edges": [
    {"from": "rd1_scene_anchor__HarborScene", "to": "GuardReply", "text": ""},
    {"from": "HarborScene", "to": "GuardReply", "text": ""}
  ]
}
```

Apply the same pattern to EVERY scene in the input, including the first one.
