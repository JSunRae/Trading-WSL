#!/bin/bash
while true; do
  ss -t | grep ESTAB >> /tmp/estab_watch.log
  sleep 1
done