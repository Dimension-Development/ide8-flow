"""Scribus scripter export: SLA → PDF. Runs INSIDE headless Scribus:

    xvfb-run -a scribus -g -ns -py export_pdf.py <in.sla> <out.pdf> <proof|package>

proof   — PDF 1.5, doc bleeds, no marks (raster proofs don't want furniture)
package — print PDF with doc bleeds, crop marks, spot colours preserved.
          PDF/X target per RND-3; version is overridable via PDFX_VERSION env
          while the spot-separation investigation iterates (see PRD §12).
"""

import os
import sys

import scribus

infile, outfile = sys.argv[1], sys.argv[2]
kind = sys.argv[3] if len(sys.argv) > 3 else "proof"

scribus.openDoc(infile)

pdf = scribus.PDFfile()
pdf.file = outfile
pdf.resolution = 300
pdf.useDocBleeds = True

# Spot colours must NOT be converted to process — RND-3. Attribute name has
# varied across scripter versions; set every spelling that exists.
for attr in ("usespot", "useSpotColors", "UseSpotColors"):
    if hasattr(pdf, attr):
        setattr(pdf, attr, True)

if kind == "package":
    # RND-3 root cause: outdst defaults to 0 (screen), which converts all
    # colour to RGB — spot separations cannot survive that path regardless
    # of usespot. Printer output keeps the named /Separation.
    pdf.outdst = 1
    pdf.cropMarks = True
    pdf.markOffset = 8.5  # clear of the bleed
    # PDF version: 15 = PDF 1.5. PDF/X values (X-3/X-4) require CMS + output
    # intent and are part of the RND-3 iteration; default stays plain PDF
    # with spots until the named-separation acceptance test passes.
    pdf.version = int(os.environ.get("PDFX_VERSION", "15"))
    info = os.environ.get("PDFX_INFO")
    if info and hasattr(pdf, "info"):
        pdf.info = info
else:
    pdf.version = 15

pdf.save()
scribus.closeDoc()
