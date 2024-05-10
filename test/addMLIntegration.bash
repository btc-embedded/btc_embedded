#!/bin/bash

EP_MATLAB_PATH="/opt/ep/matlab"
BTCEP_JAR_PATH="/opt/ep/btc_ep.jar"
MATLAB_TOOLBOX_PATH="/opt/matlab/toolbox/local"

unzip -d "$EP_MATLAB_PATH" "$BTCEP_JAR_PATH" scripts/* spec/* x64/* linux/*
mkdir "$EP_MATLAB_PATH/java"
mv "$BTCEP_JAR_PATH" "$EP_MATLAB_PATH/java/"
sudo mv "$EP_MATLAB_PATH/scripts/m/init/btc_eprc.m" "$MATLAB_TOOLBOX_PATH/"

echo "$EP_MATLAB_PATH/java/btc_ep.jar" >> "$MATLAB_TOOLBOX_PATH/classpath.txt"

echo "if (isempty(which('btc_eprc')))" >> "$MATLAB_TOOLBOX_PATH/matlabrc.m"
echo "   rehash toolboxcache" >> "$MATLAB_TOOLBOX_PATH/matlabrc.m"
echo "end" >> "$MATLAB_TOOLBOX_PATH/matlabrc.m"
echo "btc_eprc;" >> "$MATLAB_TOOLBOX_PATH/matlabrc.m"
