#!/bin/bash

declare -a list=( "binanceus" "ftx" "kucoin" "ascendex" )


for exchange in "${list[@]}"; do
  echo ""
  echo "========================"
  echo "    ${exchange}"
  echo "========================"
  echo ""
  bash user_data/strategies/scripts/test_monthly.sh ${exchange}
  echo ""
done

