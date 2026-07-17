# document.extract_pdf_text

Extract readable text from a local PDF into stdout or a text file.

## Usage

```bash
document.extract_pdf_text /workspace/input.pdf /workspace/output.txt
```

The second argument is optional. Without it, extracted text is printed to stdout.

If you provide an output path, keep it inside `/workspace` or one of its child
directories. Do not write extracted text to `/tmp` or other external paths when
running inside a restricted agent workspace.

## Environment

No service credentials are required.

## Side Effects

Reads a local PDF and optionally writes a local text file.
