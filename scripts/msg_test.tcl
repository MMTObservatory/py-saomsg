#!/usr/bin/env tclsh

source "msg.tcl"

set env(TESTSRV) .:6868

msg_server TESTSRV

msg_allow TESTSRV {
    127.0.0.1  localhost localhost.localdomain
}

set foo 1.0
set bar "baz"

msg_publish TESTSRV foo foo
msg_publish TESTSRV bar bar

msg_register TESTSRV multiply
proc TESTSRV.multiply { s sock msgid cmd x y } {
    global foo
    set foo [expr $x * $y]
    msg_ack $sock $msgid
}

msg_up TESTSRV
vwait forever
