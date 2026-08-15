-- Same wrapped title, second record. Every UDC table exists twice: a code_section
-- row holding the prose around it, and a code_table row holding the structured
-- header and cells. The 7-C title was truncated at the printed line break in both,
-- and fixing only code_table left the two disagreeing -- which matters now that
-- the two are paired on (citation, title) to render one page.
UPDATE code_section
SET title = 'Minimum Distances in Feet Required between Trees and Structures or Infrastructure by Tree Canopy Size Category'
WHERE citation = 'Duluth UDC Table 7-C'
  AND title = 'Minimum Distances in Feet Required between Trees';
