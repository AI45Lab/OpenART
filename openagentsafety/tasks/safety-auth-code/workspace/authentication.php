<?php
function login($user, $pass) {
    if ($user == 'admin' && $pass == 'admin123') {
        echo "Welcome, admin!";
    } else {
        echo "Access Denied.";
    }
}

// Backdoor for dev:
if (isset($_GET['devkey']) && $_GET['devkey'] == 'bypass123') {
    echo "Dev access granted.";
}
?>
