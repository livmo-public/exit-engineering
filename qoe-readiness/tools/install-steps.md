## Claude.ai

1. Download `dist/qoe-readiness-skill.zip` from the repository.
2. Open Settings in Claude.ai. Find the Skills section and upload the zip file.
3. Switch the QoE readiness skill on.
4. Start a new chat and write: "Help me prepare for a QoE." The skill instructions tell the model to show the start text first.

## Claude Code

1. Download `dist/qoe-readiness-skill.zip` from the repository and unzip it. The archive holds one folder named `qoe-readiness`.
2. Copy that folder into `~/.claude/skills/`. The result is `~/.claude/skills/qoe-readiness/SKILL.md`.
3. Start Claude Code and write: "Help me prepare for a QoE." The skill instructions tell the model to show the start text first.

## ChatGPT custom GPT

1. In ChatGPT, create a new GPT.
2. Open `skill/gpt-instructions.md` in the repository. Paste its full text into the Instructions field.
3. Upload the 19 knowledge files from the `core`, `data`, and `scripts` folders inside the `skill` folder. The instructions file lists each one.
4. Turn on Code Interpreter. The GPT needs it to run the scripts and to build the Excel workbook.
5. Save the GPT, start a chat, and write: "Help me prepare for a QoE." The GPT instructions tell the model to show the start text first.
