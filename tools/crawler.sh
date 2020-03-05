#!/bin/bash
REPEAT=1000
RESOLUTION=8
SAVE_DIR=$HOME/.cache/himawaripy-vid

for i in $(seq 1 $REPEAT)
do
    echo $i
    # himawaripy -l $RESOLUTION --output-dir $SAVE_DIR --dont-change
    cp $HOME/.cache/himawaripy/*.png $SAVE_DIR/$(date +%y%m%d_%H%M)00.png
    sleep 10m
done

# VIDEO_NAME=$(date +%y%m%d).mp4
# ffmpeg -framerate 10 -i $SAVE_DIR/%d.png -c:v libx264 -crf 25 $VIDEO_NAME
# mv $VIDEO_NAME $HOME/Videos
