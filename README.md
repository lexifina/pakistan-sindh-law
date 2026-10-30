# Sindh: law history in git

The Acts and Ordinances of the Province of Sindh (Pakistan) as a git history: one file per section, one paragraph per line, so `git blame`, `git log` and `git diff` work line by line. The text is the English codified text published by the Law, Parliamentary Affairs and Criminal Prosecution Department, Government of Sindh, on the Sindh Code.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law).

## What this repository holds

**Current text only, not yet a history.** The Sindh Code publishes each codified Act or Ordinance as one PDF, "updated till" a stated date, with no earlier consolidated text. So each law is one commit holding its whole text as of that date, credited to the department ("oldest version available"), not to an amending Act.

| Folder | What |
| --- | --- |
| one folder per law (by its short title, e.g. `sind-katchi-abadis-act-1987/`) | the law as codified: `000-title.md` (title, number, date and preamble), one file per section, one per Schedule (`z01-schedule.md`, ...) |
| `data/amendments.csv` | every footnote of the codified text, which says which Act substituted, inserted or omitted which words |

Only the Sindh Code's "Codified Laws" are included, added in parts as each is read and checked. A law is left out until it can be read reliably: PDFs the site could not serve, layouts the parser does not yet handle, and any law whose text fails the independent check below. Uncodified Acts (as passed), Rules and Bills are not included.

## Source

[Sindh Code, Codified Laws](https://sindhlaws.gov.pk/SindhGazetteDetail.aspx?X=ACT&CODIFIED=1), Law, Parliamentary Affairs and Criminal Prosecution Department, Government of Sindh: English PDFs marked "Official Digital Copy" and "Codified Version". Each PDF's sha256 is recorded with its version in `data/versions.json`.

## Dates

Each law's version is dated by the day its Sindh Code page says the codified text is "updated till", at noon in Karachi. That is the day the department's codification reaches, not the day of the last amendment.

## How it is built

Lexifina reads the sources listed here and records each act's dated versions, and the laws that made each change, in one corpus file. `tools/build.py` writes this repository from that file, and the same corpus always gives the same commit hashes; `REPRODUCE.md` gives the details and the checks. A model (Claude) wrote Lexifina's code; it wrote no legal text, and no model runs when the history is built.

The text layer of each PDF (no OCR) becomes one file per section. The contents pages, the running head on later pages, page numbers, the "SCAN TO VERIFY" stamp and QR code that the site adds to each download, and footnote numbers are left out. The marginal note printed beside each section (its heading) is the file's heading line. The footnotes are kept in `data/amendments.csv`. The square brackets that mark amended words stay as printed. Chapter and part headings stand above the first section under them. Tables are read row by row.

## How it is checked

Every version is read back from git on the day it took effect and must match the corpus. A second, independent reading of every PDF (a different PDF engine) must contain every letter and digit of each law in the same order, with nothing in the body left out. Results are in `REPRODUCE.md`.

## What "author" means

The author of each commit is the publisher (the Law Department), with an e-mail address that cannot exist; the committer is always Lexifina.

## Limits

Only the text as of each codification's date is here: no earlier versions, and not the laws as enacted. Only part of the Sindh statute book is codified on the Sindh Code. The codified PDFs are not the authoritative text; the Acts and Ordinances as published in the Sindh Government Gazette are.

## Licence

See [LICENSE](LICENSE): the laws are reproduced under the Copyright Ordinance, 1962, s. 57(1)(q)(i). Source: Law, Parliamentary Affairs and Criminal Prosecution Department, Government of Sindh.
