#!/bin/bash
set -e

#setup a docker registry
./scripts/setup_registry.sh

# pre-pull and store any images used for test

# build images
./scripts/build.sh

# bring up cluster
vagrant up

# run test
./scripts/run_test.sh
