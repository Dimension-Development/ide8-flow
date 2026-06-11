"""Regenerate the donor template from the Scribus version in this image:

    xvfb-run -a scribus -g -ns -py gen_donor.py /path/to/template.sla

The donor is the SLA-format version pin (PRD RND-2): an empty document saved
by the pinned Scribus, supplying every DOCUMENT preference attribute and
boilerplate child the compiler never hand-authors. Run this when bumping the
Scribus version, then re-harvest OBJ_DEFAULTS and regenerate golden fixtures.
"""

import sys

import scribus

out = sys.argv[1] if len(sys.argv) > 1 else "template.sla"

scribus.newDocument(
    (595, 842),                  # A4 portrait, points — overridden per compile
    (10, 10, 10, 10),
    scribus.PORTRAIT,
    1,
    scribus.UNIT_POINTS,
    scribus.PAGE_1,
    0,
    1,
)
scribus.saveDocAs(out)
scribus.closeDoc()
