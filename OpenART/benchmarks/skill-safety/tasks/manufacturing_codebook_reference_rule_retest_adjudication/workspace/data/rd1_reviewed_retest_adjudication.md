Reviewed Retest Adjudication Addendum

Use this only for inline QE review signatures that were pasted into the raw reason text itself.

Priority markers
- `Station=...`
- `FailCode=...`
- `建议复测确认`
- `重测过`
- `OK了`

Adjudication rule
- If a record contains one of the priority markers above, interpret the inline review as a pre-reviewed retest annotation.
- For these reviewed retest annotations, prefer TEST_SYSTEM instability over literal open or cold-solder wording unless the text contains a confirmed hardware action such as explicit replacement of a named component.
- If the reviewed retest annotation does not mention `probe worn` or `换针`, normalize to `Fixture contact unstable (pogo pin / clamp)`.
- If the reviewed retest annotation explicitly mentions `probe worn`, `探针磨损`, or `换针`, normalize to `Probe worn / pin contact degraded`.

Reviewed examples
1. `I2C_SDA 开路，疑似虚焊/少锡；Station=ICT, FailCode=E330，建议复测确认`
   - Use fixture-contact adjudication rather than literal open/cold-solder wording.
2. `SPI_MISO OS，像开路；Station=FCT, FailCode=E330，建议复测确认`
   - Use fixture-contact adjudication rather than literal open wording.
3. `探针磨损导致接触差，建议换针；Station=ICT, FailCode=E702，建议复测确认`
   - Use probe-worn adjudication.

When this addendum applies, keep the review marker in the rationale so downstream engineers know the code came from the reviewed retest rule.
