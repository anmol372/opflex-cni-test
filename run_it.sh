#!/bin/bash
: ${count:=10}

echo "Run test $count times"
for i in $(seq 1 $count)
do
    echo "Attempt $i..."
    ./scripts/run_test.sh
    retVal=$?
    if [ $retVal -ne 0 ]; then
        echo "Attempt $i failed"
        exit 1
    fi

done
