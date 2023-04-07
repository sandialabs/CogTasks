#!/bin/bash

# prepare lisp to run act-r by installing quicklisp, installing it, then running act-r for the first time which auto-installs several packages.
# this only needs to be done once, so for the docker image it is invoked by the Dockerfile.

# lisp doesn't respect the http_proxy environment variable, so instead pull it out into a parameter if it is set.
if [ "$http_proxy" != "" ]; 
  then INSTALL_ARGS=":proxy \"$http_proxy\""; 
fi

lisp -e '(load "dist/quicklisp.lisp")' -e "(quicklisp-quickstart:install $INSTALL_ARGS)" -e '(defvar *force-local* t)' -e '(load "../actr7.x/load-act-r.lisp")'
