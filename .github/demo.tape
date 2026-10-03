# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

Output .github/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 600
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms

Hide
Type "export PS1='$ ' && clear"
Enter
Show

Type "poetry run ap2-iso20022-mcp --version"
Enter
Sleep 2s

Type "poetry run python examples/01_ap2_to_pain001.py"
Enter
Sleep 3s

Type "poetry run python examples/03_guardrails.py"
Enter
Sleep 4s
