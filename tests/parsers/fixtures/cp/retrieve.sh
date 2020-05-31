#!/bin/bash
set -x
FOLDER=$1
PREFIX=$2

for f in ${FOLDER}/${PREFIX}*
do
    cp "$f" "aiida.${f##*.}" -v
done
cp "${FOLDER}/${PREFIX}_51.save/"{data-file-schema.xml,print_counter} . -v
cp "${FOLDER}/aiida.out" . -v
