# opflex-cni-test
System tests for oplex-cni overlay. 

  - Pulls the aci-containers repo (currently only the demo branch)
  - Sets up a local docker registry
  - Builds inside a container
  - Pushes the artifacts to the local registry
  - Brings up a 3 node k8s vagrant cluster, set to use the local registry
  - Runs tests in the test directory inside a docker container.
  
## How to run
**Pre-requisites**

  A ubuntu machine with the following installed:
  
    - Virtual Box
    - Vagrant
    - Docker
    - dep
    - git
 
 To run, simply clone this repo and execute *./run.sh* from the root of the repo. Approximate run time is 16 minutes
 To clean up, execute *./cleanup.sh*
 
 ## How to add tests
 Tests are run using pytests. New tests should be added in the test directory, following the pytest methodology.
 To re-run tests after the cluster has been set up, execute *./scripts/run_test.sh*
  
