#!/bin/sh
## Email when a job is finished
cmd="$@"

MAILTO='chamber'

START_DATE=`date -Ins`
echo "######## STARTED ########"
echo "## $START_DATE "

sh -c "$cmd"
rval=$?

END_DATE=`date -Ins`
echo '######## FISNISHED ########'
echo "## $END_DATE "
echo $cmd
echo '###########################'
echo "Job Finished:
####
$cmd
####
rval  : $rval
start : $START_DATE
end   : $END_DATE" | \
mail -s "Job Finsihed: $cmd" $MAILTO

