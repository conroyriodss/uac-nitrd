# NITRD subcategory ID -> PCA mapping, v1 (2026-10-25)

Status: **NO MAPPING DERIVABLE FROM THE PUBLIC RePORTER API.** This is reference data for later Task 2 work.
It is not used by scoring.

## Request

* Map these category IDs to PCA codes using FY2023 records only:
  * current (as reported by the owner): 3710-3716, 4593-4603, 5365-5367, 516, 518, 511;
  * historical, pre-2016 (as reported by the owner): 512 HCSS, 513 HEC R&D, 514 HEC I&A, 515 HCI&IM, 517
    SEW.
* Guard: no FY2024 or FY2025 record is queried. Every request body was asserted to exclude FY2024 and
  FY2025, and every returned record was checked.

## Method

RePORTER API `POST /v2/projects/search`, 2026-10-25.

* Filter: `spending_categories` = the single ID. Fields: `ApplId`, `FiscalYear`,
  `SpendingCategories`, `SpendingCategoriesDesc`.
* Each ID's name = the category name common to every returned record.

## Result

| Query | Records |
| --- | --- |
| Each of the 29 IDs above, FY2023 | 0 |
| Each of the 29 IDs above, FY2008/10/12/14/15/16/18/20/21/22/23 combined | 0 |
| Control: category 329 (NITRD parent), FY2023 | 4,583 (name "Networking and Information Technology R&D (NITRD)") |

Other checks:
* Across 300 FY2023 category-329 records, 189 distinct spending-category IDs occur. None is in the list
  above.
* No category name on those records is a NITRD PCA or subcategory. The only AI-related name is "Machine
  Learning and Artificial Intelligence", which is a separate RCDC category, not a NITRD subcategory.

## Conclusion

* The public RePORTER API does not expose these IDs, current or historical, in any year sampled.
* The IDs are probably visible only in internal RCDC/QVR views. That is the owner's source, not verified
  here.
* The only public NITRD-subcategory evidence remains the RCDC exports (File A = AI subcategories, B, C),
  which carry category NAMES, not IDs.
* So a Task 2 subcategory key would need an internal export or a QVR pull. It cannot come from RePORTER.

If the owner supplies an internal ID -> name listing, it gets recorded as v2 of this file with its
source.
