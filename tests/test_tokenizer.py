from mutohplot.hpgl.tokenizer import HPGLTokenizer

def test_tokenizer_basic_commands():
    commands = HPGLTokenizer().tokenize("IN;SP1;PA10,20;")
    assert [c.name for c in commands] == ["IN", "SP", "PA"]
    assert commands[1].numeric_args == [1.0]
    assert commands[2].numeric_args == [10.0, 20.0]


def test_label_uses_etx_terminator_and_may_contain_semicolon():
    commands = HPGLTokenizer().tokenize("IN;LBA;B\x03;PA10,20;")

    assert [command.name for command in commands] == ["IN", "LB", "PA"]
    assert commands[1].payload == "A;B"


def test_label_accepts_legacy_semicolon_terminator():
    commands = HPGLTokenizer().tokenize("LBBristol Hackspace;PU;")

    assert commands[0].name == "LB"
    assert commands[0].payload == "Bristol Hackspace"


def test_numeric_commands_may_omit_semicolon_between_mnemonics():
    commands = HPGLTokenizer().tokenize("INSP1PU0,0PA100,400DR0,1LBText\x03PD;")

    assert [command.name for command in commands] == [
        "IN",
        "SP",
        "PU",
        "PA",
        "DR",
        "LB",
        "PD",
    ]
    assert commands[3].numeric_args == [100.0, 400.0]
    assert commands[4].numeric_args == [0.0, 1.0]


def test_rectangle_commands_may_be_followed_by_pen_up_without_semicolon():
    commands = HPGLTokenizer().tokenize(
        "PU2550,0EA2550,10870PU-15970,0RA-15970,10870PU0,0;"
    )

    assert [command.name for command in commands] == [
        "PU",
        "EA",
        "PU",
        "RA",
        "PU",
    ]
    assert commands[1].numeric_args == [2550.0, 10870.0]
    assert commands[2].numeric_args == [-15970.0, 0.0]
    assert commands[3].numeric_args == [-15970.0, 10870.0]
