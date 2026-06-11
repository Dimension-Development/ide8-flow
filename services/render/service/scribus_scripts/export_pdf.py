"""Scribus scripter export: SLA → PDF. Runs INSIDE headless Scribus:

    xvfb-run -a scribus -g -ns -py export_pdf.py <in.sla> <out.pdf> <proof|package>

proof   — PDF 1.5, doc bleeds, no marks (raster proofs don't want furniture)
package — PDF/X-4 by default: printer output, doc bleeds, crop marks, named
          spot separations, output intent. Env overrides: PDFX_VERSION
          (10=X-4, 11=X-1a, 12=X-3, 13..16=plain PDF 1.3-1.6), PDFX_PROFILE
          (output intent), PDFX_INFO (info string — PDF/X requires non-empty).
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
    # Formal PDF/X: 10 = X-4 (default), 11 = X-1a, 12 = X-3. Conformance
    # needs colour management on, an output intent profile, and a non-empty
    # info string — all three levels verified to keep named spot separations.
    pdf.version = int(os.environ.get("PDFX_VERSION", "10"))
    pdf.profiles = 1
    pdf.printprofc = os.environ.get("PDFX_PROFILE",
                                    "ISO Coated v2 300% (basICColor)")
    pdf.info = os.environ.get("PDFX_INFO", "ide8.flow package")
else:
    pdf.version = 15

pdf.save()
scribus.closeDoc()
