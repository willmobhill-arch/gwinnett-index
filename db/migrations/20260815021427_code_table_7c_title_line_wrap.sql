-- Table 7-C's title wraps across two printed lines on page 210:
--
--     Table 7-C. Minimum Distances in Feet Required between Trees
--     and Structures or Infrastructure by Tree Canopy Size Category
--
-- The extractor took line one and stopped. "Minimum Distances in Feet Required
-- between Trees" is a grammatical, plausible-looking title that drops the entire
-- subject of the table -- distances between trees and *structures or
-- infrastructure*, banded by canopy size. Nothing about the stored value looks
-- wrong; it reads as a complete title.
--
-- Found by prefix-testing every title in tests/fixtures/duluth_udc_tables.json
-- against the rendered PDF. 7-C is the only one of the 20 that disagreed.
UPDATE code_table
SET title = 'Minimum Distances in Feet Required between Trees and Structures or Infrastructure by Tree Canopy Size Category'
WHERE citation = 'Duluth UDC Table 7-C'
  AND title = 'Minimum Distances in Feet Required between Trees';
