# msg.tcl Message Interface
#
# Copyright Smithsonain Institution 2006

package provide msg 2.0

set msg_logger	{}

set MsgSetting {}

proc msg_debug { args } {
	global env

    catch {
	if { $env(MSGDEBUG) != 0 } {
 	    puts "[clock format [clock seconds]] $args"
	}
    }
}

proc msg_abort { server { msgid {} } } {
    upvar #0 $server S

    set $S(id,$$S(msgid)) -4
}

proc msg_wait { server msgid { cmd {} } } {
	msg_debug Wait: $server $msgid
	upvar #0 $server S

    if { [lindex $S(id,$msgid) 0] == 0 } {
	vwait ${server}(id,$msgid)
    }

    msg_debug Wait: $server $msgid continue
    catch { after cancel $S(to,${msgid})
	        msg_debug "Timeout Canceled: $S(to,${msgid})"
    }
    #catch { after cancel $S(reopen_timer) }

    set value $S(id,$msgid)

    unset S(id,${msgid})

    catch { unset S(to,${msgid})	}

    if { [lindex $value 0] == -1 } {
	error [lrange $value 1 end]
    }
    if { [lindex $value 0] == -2 } {
        error "timeout $msgid $cmd"
    }
    if { [lindex $value 0] == -3 } {
        error "server dead $msgid $cmd"
    }
    if { [lindex $value 0] == -4 } {
        error "msg wait aborted $msgid $cmd"
    }
    if { [lindex $value 0] ==  1 } {
	return  [concat [lrange $value 1 end]]
    }
}

proc msg_waitgroup { server group } {
    upvar #0 $server S

    set result {}
    set errors {}

    foreach msgid $S($group) {
	if { [catch { lappend result [msg_wait $server $msgid] } error] } {
	    lappend errors $error
	}
    }
    unset S($group)


    if { $errors != {} } {
	error $errors
    } else {
        return $result
    }
}

proc msg_timeout { server msgid } {
	msg_debug Timeout: $server $msgid
	upvar #0 $server S

    set S(id,$msgid) -2
}

proc msg_reopen { server } {
	msg_debug Reopen: $server
	upvar #0 $server S

    set S(up) 0


    catch { after cancel $S(reopen_timer) }

    if { [catch {
	set sock [msg_setsock $server]
        set S($sock) [lindex [fconfigure $sock -peername] 1]
    }] } {
        catch { after cancel $S(reopen_timer) }
        set S(reopen_timer) [after $S(reopen) "msg_reopen $server"]
    }

}

proc msg_cmd { server cmd { timeout {} } { sync sync } { code {} } } {
	upvar #0 $server S


    if { [string compare $sync nowait] } {
        set msgid $S(N)
        incr S(N) 2
    } else {
	set msgid 0
    }

    set sock $S(sock)
    set line [join [concat $msgid $cmd]]

    msg_debug Msg: $line

    if { [catch {
	if { [catch {
	    puts $sock $line
            flush $sock
	}] } {
	    if { $S(up) } {
		set sock [msg_setsock $server]
		puts $sock $line
		flush $sock
	    } else {
		return -3
	    }
	}
    }] } {
	msg_kilclient $server $sock
        set S(reopen_timer) [after $S(reopen) "msg_reopen $server"]
	error "server down: $server"
    }

    if { [string compare $timeout {}] == 0 } {
	set timeout $S(timeout)
    }

    if { [string compare $sync nowait] } {
	set S(id,${msgid}) 0
	set S(to,${msgid}) [after $timeout "msg_timeout $server $msgid"]
    }

    set S(cb,${msgid}) $code
    set S(sy,${msgid}) $sync

    if { ![string compare $sync sync] } {
	msg_wait $server $msgid $cmd
    } elseif { ![string compare $sync async] } {
	return $msgid
    } else {
	lappend S($sync) $msgid
	return $msgid
    }
}

proc msg_close { server } {
    upvar #0 $server S
	close $S(sock)
    if { [ string compare $S(logfile) NULL ] != 0 } {
	close $S(logfile)
    }
}

proc msg_sock { server } {
    upvar #0 $server S
	return $S(sock)
}

proc prstack { } {
    for { set i 0 } { $i < [info level] } { incr i } {
	puts [info level $i]
    }

    foreach after [after info] {
        puts "$after [after info $after]"
    }
}


proc msg_getline { server sock } {
	upvar #0 $server S

    set len 0
    set err [catch { set len [gets $sock line] }]
    if { $len < 0 || $err == 1 } {
	if { $S(type) == 1 } {
	    msg_debug Kil Server $server
            msg_kilclient  $server $sock
	}
	if { $S(type) == 2 } {
	    msg_debug Kil Client $S($sock) cannot read line from client
            msg_kilclient  $server $sock
        }

	close $sock
	set S(sock) ""

	if { $S(type) == 1 } {
	    set S(connection) Down

	    if { [catch { uplevel #0 $S(done) }] == 1 } {
		    global errorInfo

		tk_messageBox -icon error -type ok  \
		      -message "Error executing client done code: $errorInfo"
	    }

	    catch { after cancel $S(reopen_timer) }
	    set S(reopen_timer) [after $S(reopen) "msg_reopen $server"]

	}
	return {}
    }

    return $line
}

proc msg_handle { server sock } {
	upvar #0 $server S

    set line [msg_getline $server $sock]

    if { [string compare $line {}] == 0 } { return }

    if { [string match {[+0123456789]*} $line] == 0 } {
	set line "0 $line"
    }
    msg_debug Handle: $line
    if { [catch {
        set msgid  [lindex $line 0]
        set cmd    [lindex $line 1]
        set arg    [lindex $line 2]
    }] } {
	error "Bad line from client: $line"
    }
    msg_logmsg $server "Command" "$cmd $arg"

    if { [catch { interp eval $server $cmd $server $sock $line } error] } {
	msg_nak $sock $msgid $error
	msg_logmsg $server "Error" "$cmd $arg"
    }
}

proc msg_set { server name value { timeout {} } { sync sync } } {
    if { ![string compare $sync {}] } {
	set sync sync
    }
    msg_cmd $server "set $name $value" $timeout $sync
}

proc msg_get { server name { timeout {} } { sync sync } { code {} } } {
    if { ![string compare $sync {}] } {
	set sync sync
    }
    msg_cmd $server "get $name" $timeout $sync $code
}

proc msg_blk { server name leng { timeout {} } { sync sync } { code {} } } {
    if { ![string compare $sync {}] } {
	set sync sync
    }
    msg_cmd $server "get $name $leng" $timeout $sync $code
}

proc msg_list { server P { timeout {} } } {
        upvar #0 $server S
	upvar $P p

    set sock $S(sock)

    msg_cmd $server "lst" $timeout
    while { 1 } {
        if { ![string compare				\
		[set line [msg_getline $server $sock]]  \
		"----LIST----"] } {
		break
	}
	lappend p "[lindex $line 0] [lindex $line 1] [list [lrange $line 2 end]]"
    }
}

proc msg_alarmhandler { } {
	global ALARM

	upvar #0 $ALARM S
	set S(reopen) 60000
}

proc msg_alarm { server secs } {
	upvar #0 $server S
	global ALARM

  catch {
    if { $secs } {
	set S(sigalarm) [signal get ALRM]

	signal trap ALRM msg_alarmhandler
	set ALARM $server
	alarm $secs
    } else {
	alarm 0
	signal set $S(sigalarm)
    }
  }
}

proc msg_aset { args } {
	puts $args
}

proc msg_setsock { server } {
	upvar #0 $server S
	msg_debug Sock: $server $S(host) $S(port)

    set host $S(host)
    set port $S(port)

    msg_debug DoSock: $server $S(host) $S(port) $S(reopen)
    msg_alarm $server 2

    catch { close $S(sock) }
    catch { msg_kilclient $server $S(sock) }

    if { [catch { set sock [socket $host $port] }] } {
	    global errorInfo

	msg_alarm $server 0
	error "host down : $server"
    }
    msg_debug DoneSock: $server $S(host) $S(port)
    set S(sock) $sock

    fileevent $sock readable "msg_handle $server $sock"
    fconfigure $sock -buffering line

    msg_alarm $server 0
    set $S(up) 0

    if { [catch { uplevel #0 $S(init) }] == 0 } {
	if { [catch {
	    # Re-sync the variables in the message map
	    #
	    set up $S(up)

	    set wait {}

	    foreach m $S(+vars) {
		set var  [lindex $m 0]
		set name [lindex $m 1]
		set init [lindex $m 2]

		global   $var
		upvar #0 $var v

		if { [string compare $init Server] == 0 \
		 || ([string compare $init Up]     == 0 && $S(up) == 1) } {
		    lappend wait [msg_get $server $name 30000 resync "msg_aset $var"]
		}
		if { [string compare $init Client] == 0 \
		 || ([string compare $init Up]     == 0 && $S(up) == 0) } {
		    lappend wait [msg_set $server $name $v 30000 resync]
		}
	    }
	    if { [string compare $wait {}] } { msg_waitgroup $server resync }

	    set #S(up) $up
	}] != 0 } {
		close $sock
		error "Error syncing mapped vars with $server"
	}

	if { [catch {
	    set wait {}

	    # Re-establish the subscriptions
	    #
	    if { [string compare $S(+subs) {}] != 0 } {
		set wait {}

		foreach sub $S(+subs) {
		    lappend wait [msg_cmd $server "sub [lindex $sub 0] [lindex $sub 3]" 30000 subscribe]
		}
	        if { [string compare $wait {}] } {
		    msg_waitgroup $server subscribe
		}
	    }
	} ] != 0 } {
		close $sock
		error "Error re-establishing subscriptions with $server"
	    }
    } else {
		close $sock

		error "Error in client init code $::errorInfo"
    }

    # try retry here maybe?

    set S(up) 1
    set S(connection) Up
    set S(reopen) 1000

    msg_debug Sock: DONE
    return $sock
}

proc ackdone { id server index op } {
    upvar $server S

    set response [lindex $S($index) 0]

    if { $S(up) } {
	if  { $response == -2 } {
	    if { $S(hung) == 0 } {
		set S(hung) 1
		set S(connection) Hung
	    }
	} else {
	    if { $S(hung) == 1 } {
		set S(hung) 0
		set S(connection) Up
	    }
	}
    }
    trace vdelete  S($index) wu "ackdone $id"
    unset S($index)
    after cancel $S(to,${id})
    catch { unset S(to,${id}) }
}

proc msg_keepalive { server timeout updatetime} {
    upvar #0 $server S
    if { ![info exists S(hung)] } {
	set S(hung) 0
    }
    if { $S(up) } {
	catch { set id [msg_cmd $server ack $timeout async]
	    if { [info exists S(id,$id)] } {
		trace variable S(id,$id) wu "ackdone $id"
	    }
	}
    }

    after $updatetime "msg_keepalive $server $timeout $updatetime"
}

proc msg_uplevel { code args } {
	uplevel #0 $code $args
}

proc msg_subscribe { server name var { code {} } { update {} } { timeout {} } { sync sync } } {
	msg_debug CSub: $server $name
	upvar #0 $server S

	if { ![string compare $update {}] } {
		set update 1
	}

	set S($name) $var
	lappend S(+subs) [list $name $var $code $update]
	if { [string compare $code {}] != 0 } {
	    global $var
	    trace variable $var w [list msg_uplevel $code]
	}

	if { $S(up) } { catch { msg_cmd $server "sub $name $update" $timeout $sync } }
}

proc msg_slst { server sock msgid lst } {
	msg_debug SLst: $server $sock $msgid
	upvar #0 $server S

	msg_ack $sock $msgid

	puts $sock "server	$server	$S(name)"

	foreach { var comment } [array get S P,*] {
	    msg_debug  "published	[string range $var 2 end]	$comment"
	    puts $sock "published	[string range $var 2 end]	$comment"
	}
	foreach { cmd comment } [array get S R,*] {
	    msg_debug  "registered	[string range $cmd 2 end]	$comment"
	    puts $sock "registered	[string range $cmd 2 end]	$comment"
	}
	msg_puts $sock ----LIST----
}

proc msg_slog { server log } {
    msg_log $server $log
}

proc msg_sget { server sock msgid get name args } {
	msg_debug SGet: $server $sock $msgid $name
	upvar #0 $server S

	if { [string compare $S($name) {}] == 0 } {
	    msg_nak $sock $msgid "No variable $name"
	    return
	}

	set variable $S($name)
	upvar #0 $variable var

	if { [catch { msg_ack $sock $msgid $var }] } {
	    global errorInfo
	    puts $errorInfo
	    msg_nak $sock $msgid "cannot access $name"
	}
}

proc msg_ssource { server sock msgid set args } {
    if { [string compare -length 4 $sock file] } {
	return
    }

    if { [catch { eval [read [set f [open [lindex $args 0]]]] ; close $f } reply] } { puts $reply }
}

proc msg_sset { server sock msgid set args } {
	set name  [lindex $args 0]
	set value [lrange $args 1 end]

	msg_debug SSet: $server $sock $msgid $name $value
	upvar #0 $server S

	if { [catch {
 	    set variable $S($name)
	    upvar #0 $variable var

	    set ::MsgSetting $sock
	    set var $value
	    set ::MsgSetting {}
	    msg_ack $sock $msgid
	}] } {
	    msg_nak $sock $msgid "cannot access $name"
	}
}

proc msg_sack { server sock msgid ack args } {
	msg_ack $sock $msgid $args
}

proc msg_cset { server sock msgid set args } {
	set name  [lindex $args 0]
	set value [join [lrange $args 1 end]]

	upvar #0 $server S
	msg_debug CSet: $server $sock $msgid $name $value ($S($name))

	global $S($name)

	set S(setting) $name

	if { [catch { set $S($name) $value }] } {
		global errorInfo
	        puts "Can't set $S($name) : $errorInfo"
	}

	set S(setting) {}
}

proc msg_cnak { server sock msgid ack args } {
	upvar #0 $server S

    set arg [join $args]
    set S(id,$msgid) "-1 $arg"

    unset S(cb,${msgid})
    unset S(sy,${msgid})

    catch { after cancel $S(to,${msgid})
            msg_debug "CNak Timeout Canceled: $S(to,${msgid})"
	    unset S(to,${msgid})
    }
}

proc msg_cack { server sock msgid ack args } {
	upvar #0 $server S

    set arg [join $args]

    if { [string compare $S(cb,${msgid}) {}] } {
        set S(id,$msgid) [eval $S(cb,${msgid}) $server $sock $msgid $ack $args]
	if { ![string compare $S(sy,${msgid}) async] } {
    	    unset S(id,${msgid})
	}
    } else {
        set S(id,$msgid) "1 $arg"
    }

    catch { unset S(cb,${msgid}) }
    unset S(sy,${msgid})

    catch {
        msg_debug "CAck Timeout Canceled: $S(to,${msgid})"

	after cancel $S(to,${msgid})
	unset S(to,${msgid})
    }
}

proc msg_nak { sock msgid args } {
    msg_debug Nak: $sock $msgid $args
    if { $msgid != 0 } {
	msg_puts $sock $msgid nak $args
    }
}

proc msg_ack { sock msgid args } {
    msg_debug Ack: $sock $msgid $args
    if { $msgid != 0 } {
	msg_puts $sock $msgid ack [join $args]
    }
}

proc msg_rpy { sock msgid args } {
    msg_debug Rpy: $sock $msgid $args
    if { $msgid != 0 } {
	msg_puts $sock $msgid $args
    }
}
proc msg_security { server peer } {
	upvar #0 $server S
    return 1
}

proc msg_checkhost {hostname allow deny} {
    set host [string tolower $hostname]
    for {set i 0} {$i <= [expr [llength $allow] - 1]} {incr i 1} {
	if {[msg_matchone $host [lindex $allow $i]] == 1} {
	    return 1
	}
    }
    for {set j 0} {$j <= [expr [llength  $deny] - 1]} {incr j 1} {
	if {[msg_matchone $host [lindex  $deny $j]] == 1} {
	    return 0
	}
    }
    return 1
}


proc msg_matchone {hostname pattern} {

        set host [split $hostname .]
        set pat  [split $pattern .]

        regsub {\*} $pat {.*} pat

	set lenpat  [llength $pat]
        set lenhost [llength $host]

    if {$lenhost < $lenpat} {
	return 0
    }
    if {$lenpat < $lenhost} {
	for {set c 0} {$c < [expr $lenhost - $lenpat]} {incr c 1} {
	    set pat [linsert $pat 0 .]
	}
    }
    for {set i $lenhost} {$i > 0} {incr i -1} {
	set j [expr $i - 1]
	set phost [lindex $host $j]
	set ppat [lindex $pat $j]
	if ![regexp ^$ppat$ $phost] {
	    if {$ppat == "."} {
		return 1
	    } else {
		return 0
	    }
	}
    }
    return 1
}




proc msg_accept { server sock addr port } {
	upvar #0 $server S

    set peer [lindex [fconfigure $sock -peername] 1]
    set S($sock) $peer

    msg_debug New Client from $peer

    if { [msg_security $server $peer] == 1 } {
	fileevent $sock readable "msg_handle $server $sock"
	fconfigure $sock -buffering line
	msg_logmsg $server "Newclient" "$S($sock) $sock"
    } else {
	msg_debug Kil Client no permission for $peer
	msg_logmsg $server "Kilclient" "$S($sock) $sock" "permission denied"
	close $sock
    }

    return
}

proc msg_init { server address type } {
	global env
	upvar #0 $server S


    if { [string compare $address {}] == 0 } {
	set name [string toupper $env($server)]
    } else {
	set name $address
    }

    set host [lindex [split $name : ] 0]
    if { [string compare $host "."] == 0 } {
	set host [info hostname]
    }
    set port [lindex [split $name : ] 1]

    set S(server)	$server
    set S(up) 		    0
    set S(connection) Down
    set S(timeout) 	 5000
    set S(reopen)  	 1000
    set S(hosts.allow) $host
    set S(hosts.deny)  { * }
    set S(logfile)      NULL
    set S(log)          NULL
    set S(N) 		$type

    set S(type) 	$type
    set S(name) 	$name
    set S(host) 	$host
    set S(port) 	$port

    set S(setting)	{}

    msg_debug Init: $server name: $name host: $host port: $port

    catch { interp delete $server }
    #interp create -safe $server
    interp create $server
}

proc msg_down { server } {
	upvar #0 $server S

    set sock $S(sock)
    close $sock

#    set clients ""
#    catch { set clients $S(+$name) }

#    foreach sock $clients {
#	close $sock
#    }
}

proc msg_up { server } {
	msg_debug Up: $server
	upvar #0 $server S

    set port $S(port)
    set S(sock) [socket -server "msg_accept $server" $port]
}

proc msg_isup { server } {
	upvar #0 $server S

	return $S(up)
}


proc msg_server { server { address {} } { log {} } } {
    upvar #0 $server S
    global msg_logger
    msg_init $server $address 2
    msg_log $server $log

    interp eval $server rename set \{\}
    interp alias $server set    {} msg_sset
    interp alias $server get    {} msg_sget
    interp alias $server lst    {} msg_slst
    interp alias $server sub    {} msg_ssub
    interp alias $server ack    {} msg_sack
    interp alias $server log    {} msg_slog
    interp alias $server source {} msg_ssource
    #DLC - start#
    interp alias $server spargs {} msg_srvproc_arglst
    #end#
    msg_publish $server log msg_logger

    set msginit .
    catch { set msginit $::env(MSGINITDIR) }

    if { [file exists $msginit/[string tolower $server].rc] } {
	msg_fakclient $server $msginit/[string tolower $server].rc
    }
}

proc msg_client { server { init { } } { done { } } { address {} } } {
	upvar #0 $server S

    if { [info exists ::$server] } {
	puts stderr "Global variable $server exists : cannot open client connection"
	return
    }
    msg_init $server $address 1

    set S(init) $init
    set S(done) $done
    set S(sock) ""
    set S(+subs) ""
    set S(+vars) ""


    #interp eval $server rename set \{\}
    interp eval $server rename set _set
    interp alias $server set {} msg_cset
    interp alias $server ack {} msg_cack
    interp alias $server blk {} msg_cack
    interp alias $server nak {} msg_cnak

    msg_reopen $server
}

# Server side access control
#
proc msg_allow { server allow } {
	upvar #0 $server S

    set S(hosts.allow) $allow
}
proc msg_deny { server deny } {
	upvar #0 $server S

    set S(hosts.deny)  $deny
}

# Server side bindings
#
proc msg_register { server command { comment {} } { proc {} } } {
    if { ![string compare $proc {}] } { set proc $server.$command }

    upvar #0 $server S

    set S(R,$command) $comment
    $server alias $command $proc
}

proc msg_publish { server name { var {} } { code {} } { comment {} } } {
	upvar #0 $server S

    set S($name)       $var
    set S($name,cache) {}
    set S(P,$name) $comment
    upvar #0 $var v

    if { ![info exists v] } {
	set v {}
    }
    if { [string compare $code {}] != 0 } {
	trace variable v rw $code
    }
    trace variable v w "msg_postvar $server $name"
}

proc msg_postvar { server name var index op } {
    msg_post $server $name
}

# Lowest level output
#
proc msg_puts { sock args } {
	msg_alarm $sock 3
	puts $sock [join $args]
	msg_alarm $sock 0
}

proc msg_setvar { server name code timeout sync variable indx op } {
	upvar #0 $server S
	upvar $variable value

    if { [string compare $name $S(setting)] } {
	if { $S(up) == 1 } {
	    if { $op == "r" } {
		set value [msg_get $server ${name} $timeout $sync]
	    }
	    if { $op == "w" } {
		msg_set $server ${name} $value $timeout $sync
	    }
	}
    } else {
	if { [string compare $code {}] } {
	   uplevel #0 $code $variable $indx $op
	}
    }
}

proc msg_variable { server name var mode
			{ def 0 }
			{ init {} }
			{ code {} }
			{ timeout {} }
			{ sync sync }
		  } {
	upvar #0 $server S

	global    $var
	upvar #0  ${var}   v

	if { [info exists  v] == 0 } {
	    set $var $def
	}

	set S($var) $name
	set S($var,value) $v

	lappend S(+vars) [list $var $name $init]
	if { $S(up) } {
	    if { ![string compare $init Server]
	      || ![string compare $init Up] } {
		set $S(setting) $name
		set $var [msg_get $server $name]
		set $S(setting) {}
	    }
	}

	trace variable $var $mode [list msg_setvar $server $name $code $timeout $sync]
}

proc msg_mapvar { server Map } {
 foreach m $Map {
        set var  [lindex $m 0]
        set name [lindex $m 1]
        set def  [lindex $m 2]
        set init [lindex $m 3]

	if { [string compare $init {}] == 0 } {
	    set init Up
	}

	msg_variable $server $name $var rw $def $init
 }
}

proc msg_log {server log} {
    upvar #0 $server S
    if { [string compare $log {} ] != 0 } {
	if { [file exists $log] } {
	    set S(log) $log
	    set S(logfile) [open $log a]
	    fconfigure $S(logfile) -buffering line
	}
    }
}

proc msg_logmsg {server args} {
    upvar #0 $server S
    global msg_logger

    if { [string compare $S(logfile) NULL] != 0} {
	set sec [clock seconds]
        set msg_logger "[clock format $sec] $args\n"
	puts $S(logfile) $msg_logger
    }
}

#
# Enhancements to msg.tcl to impliment subscription value
# caching and update as the C server does.
#
proc msg_ssub { server sock msgid sub name { update 1 } } {
	msg_debug SSub: $server $sock $msgid $name
	upvar #0 $server S

	if { [catch {
            upvar #0 $S($name) var

	    if { [string compare $S($name) {}] == 0 } {
		error "No variable $name"
		return
	    } }] == 1 } {
		error "No variable $name"
	}

        lappend S(+$sock) $name
	lappend S(+$name) $sock

	set S($name,$sock,update) [expr int($update * 1000)]
	set S($name,$sock,lastup) [clock clicks -milliseconds]
	set S($name,$sock,after)  {}

	if { $update < 0 } {
	    set S($name,$sock,after) [after [expr -($update)] \
			"msg_postafter $server $sock $name"]
	}

	msg_ack $sock $msgid $var
	catch { msg_puts $sock 0 set $name $var }
}

proc msg_postafter { server sock name } {
	upvar #0 $server S
	upvar #0 $S($name) var

	msg_debug PstA: $server $sock $name $var

	catch {
	    msg_puts $sock 0 set $name $var
	    set S($name,$sock,lastup) [clock clicks -milliseconds]
	}

	set update $S($name,$sock,update)

	if { $update < 0 } {
	    set S($name,$sock,after) [after [expr -($update)] \
			"msg_postafter $server $sock $name"]
	} else {
	    set S($name,$sock,after) {}
	}
}

proc msg_post { server name { post 1 } } {
	upvar #0 $server S
	upvar #0 $S($name) var

    set change [string compare $S($name,cache) $var]
    set clock  [clock clicks -milliseconds]
    set S($name,cache) $var

    set clients {}
    catch { set clients $S(+$name) }

    foreach sock $clients {
	if { ![string compare $sock $::MsgSetting] } {
	    set S($name,$sock,lastup) $clock
	    continue
	}

	msg_debug Post: $sock $name $var
	set update $S($name,$sock,update)

	if { $update > 0				\
	  && $change					\
	  && ![string compare $S($name,$sock,after) {}] } {

	    set nextup [expr ($S($name,$sock,lastup)	\
		            + $S($name,$sock,update)) - $clock]

	    if { $nextup < 0 } { set nextup 0 }

	    set S($name,$sock,after) [after $nextup 	\
			"msg_postafter $server $sock $name"]
	}
	if { $post && $update == 0 } {
	    catch {
		msg_puts $sock 0 set $name $var
	        set S($name,$sock,lastup) $clock
	    }
	}
    }
}

proc msg_kilclient { server sock } {
    upvar #0 $server S
    set peer None
    catch { set peer $S($sock) }

    msg_logmsg $server "Kilclient" "$peer $sock"
    foreach timer [array names S to,*] {
    	catch { after cancel $S($timer) }
	unset S($timer)
    }
    foreach msgid [array names S {id,[0-9]*}] {
    	catch { set S($msgid) -3 }
    }
    if { [info exists S(+$sock)] } {
	foreach name $S(+$sock) {
	    set ix [lsearch -exact $S(+$name) $sock]
	    set S(+$name) [lreplace $S(+$name) $ix $ix]

	    catch { after cancel $S($name,$sock,after) }

	    catch { array unset S($name,$sock,update) }
	    catch { array unset S($name,$sock,lastup) }
	    catch { array unset S($name,$sock,after)  }
	}
	catch { array unset S(+$sock) }
    }
}

proc rx { exp str rep } {
     regsub -all -- $exp $str $rep rx
     return $rx
}

proc msg_srvproc { server name args body } {
    msg_register $server $name
    proc $name "$args" $body
    set a {}
    foreach arg $args { lappend a [lindex $arg 0] }

    proc $server.$name [concat s sock msgid cmd $args] [subst {
        msg_ack \$sock \$msgid \[[concat $name [rx {([a-zA-Z0-9]+)} $a {$\1}]]]
    }]
}

proc msg_fakclient { server file } {
	upvar #0 $server S

    set fake [open $file r]

    set S($fake) $file
    fconfigure $fake -buffering line
    fileevent $fake readable "msg_handle $server $fake"
}

#DLC - start#
proc msg_srvproc_arglst {server sock msgid spargs procname} {
	msg_debug SPArgs: $server $sock $msgid $procname
	set arglst ""
	set pname  ${server}.$procname

	# if procname not defined, nak
	if ![llength [info procs $pname]] {
		msg_nak $sock $msgid "srvproc $procname not defined"
		return
	}

	# get arguments, reconstruct default values
	foreach arg [info args $pname] {
		if [info default $pname $arg X] {
			lappend arglst [list $arg $X]
		} else {
			lappend arglst $arg
		}
	}

	# return complete (+ defaults) argument list
	msg_ack $sock $msgid [list $arglst]
}

proc msg_cliproc { server procname {retdef false}} {
	msg_debug CliProc: $server $procname

	# get arguments for this server-side proc
	set args [msg_cmd $server "spargs $procname"]
	regexp {^s sock msgid cmd (.*)$} $args -> args

	# generate $<argname> for the local body
	foreach arg $args {
		set arg [lindex $arg 0]
		lappend dargs "\$$arg"
	}
	set body [subst -nocommands {
		return [msg_cmd $server "$procname $dargs"]
	}]

	# make/return the local (copy) procedure
	set procdef [list proc $procname $args $body]

	if $retdef {
		return $procdef
	} else {
		uplevel $procdef
	}
}

proc msg_cliproc_all { server } {
	msg_debug CliProcAll: $server

	set newprocs ""

	# run through list of server defines
	msg_list $server lst
	foreach defn $lst {

		# grab type and name of definition
		set type [lindex $defn 0]
		set name [lindex $defn 1]

		# if it's not registered (a proc), skip
		if ![string equal $type "registered"] \
			continue

		# grab and run a cliproc definition
		lappend newprocs $name
		uplevel [msg_cliproc $server $name true]
	}

	# return list of defined (copy) procedures
	return $newprocs
}
#end#
