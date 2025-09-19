#!/bin/bash
while true; do
  ps aux | grep ibgateway >> /tmp/launcher_watch.log
  sleep 1
done