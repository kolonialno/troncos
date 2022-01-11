#!/bin/bash
# Entrypoint for running management commands as well as plugging into Docker

set -o errexit
set -o pipefail
set -o nounset

# This is the repoe where the package will be published. The package name is not part of this URL.
REPO=https://europe-python.pkg.dev/nube-hub/python/

function release () {
    rm -rf dist
    poetry build
    twine upload --repository-url $REPO dist/* --verbose
}

function bump () {
    if [ -z ${1+x} ]; then
      echo "No version bump rule specified, must be one of the following:"
      echo -e "\t patch, minor, major, prepatch, preminor, premajor, prerelease"
      echo -e "\nMore info: https://python-poetry.org/docs/cli/#version"
      exit 0
    fi
    poetry version $1
}

case "$1" in
  release)
    release
    ;;

  bump)
    bump $2
    ;;
 
  bump_and_release)
    bump $2
    release
    ;;
  

esac
