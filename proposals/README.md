# Proposals

The engine writes `proposals.csv` here, with one row per fixture project (all 480):

| Column | Values |
| --- | --- |
| `appl_id` | integer Appl ID from the fixture |
| `primary_pca` | ACNS, AI, CHuman, CNPS, CSP, EdW, EHCS, ENIT, HCIA, IRAS, LSDMA, SPSQ, AW (Advanced Wireless R&D), or empty |
| `ai_relevant` | true / false; `AI` requires true |

Use PCA codes only. Never use RCDC category labels.

To freeze: run `scripts/sweep.sh --freeze`. It must PASS. Then tag the commit and log
the printed SHA-256 before the reveal. After the freeze, never edit this file.
