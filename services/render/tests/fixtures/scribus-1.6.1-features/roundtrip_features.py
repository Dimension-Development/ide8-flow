"""Open and resave every harvested SLA through the running Scribus build."""

import glob
import os
import sys

import scribus


source_dir = os.path.abspath(sys.argv[1])
out_dir = os.path.abspath(sys.argv[2])
if not os.path.isdir(out_dir):
    os.makedirs(out_dir)

for source in sorted(glob.glob(os.path.join(source_dir, "*.sla"))):
    scribus.openDoc(source)
    scribus.saveDocAs(os.path.join(out_dir, os.path.basename(source)))
    scribus.closeDoc()
