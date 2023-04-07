#!/bin/bash

### Clozure lisp (aka ccl)
#
# lisp must be run in the cogtasks directory, since actr_person.py causes lisp to load actr-person.lisp and other files from the current directory.
# 
# The following load command relies on actr7.x.zip having been unzipped next to cogtasks in the directory structure.
#
exec lisp -e '(defvar *force-local* t)' -e '(load "../actr7.x/load-act-r.lisp")'

### sbcl lisp
#
# note this has not been tested to really work.
# different lisps do not handle repeated connections/disconnections from the lisp-based server
# by the python code in the same way.  Clozure is the most stable of those tried so far.
#
# lisp --eval '(defvar *force-local* t)' --eval '(load "/home/rgabbot/rgabbot/projects/TOA/ACTR/actr_source/load-act-r.lisp")'
