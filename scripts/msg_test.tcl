#!/usr/bin/env tclsh

source "msg.tcl"

set env(TESTSRV) .:6868

msg_server TESTSRV

set foo 1.0
set bar "baz"
set fizz ""
set bazz "there once was a man"

msg_publish TESTSRV foo foo
msg_publish TESTSRV bar bar
msg_publish TESTSRV fizz fizz
msg_publish TESTSRV bazz bazz

msg_register TESTSRV multiply
proc TESTSRV.multiply { s sock msgid cmd x y } {
    global foo
    set foo [expr $x * $y]
    msg_ack $sock $msgid
}

msg_up TESTSRV
vwait forever
