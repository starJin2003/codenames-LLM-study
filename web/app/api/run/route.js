import { NextResponse } from "next/server";

function makeGrid(words) {
  let rows = [];
  for (let r = 0; r < words.length; r += 5) {
    let cells = [];
    for (let i = 0; i < 5; i++) {
      const num = r + i + 1;
      cells.push(`${num.toString().padStart(2, " ")}. ${words[r + i]}`);
    }
    rows.push(cells.join("   "));
  }
  return rows.join("\n");
}

export async function POST(req) {
  try {
    const body = await req.json();
    const { board, codemaster_system } = body;

    if (!board || board.length !== 25) {
      return NextResponse.json({ error: "Invalid board. Must have 25 tiles." }, { status: 400 });
    }
    if (!codemaster_system) {
      return NextResponse.json({ error: "Missing codemaster system prompt." }, { status: 400 });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: "GEMINI_API_KEY is not set in backend environment variables." }, { status: 500 });
    }

    const words = board.map(tile => tile.word.toUpperCase());
    const key = {};
    board.forEach(tile => {
      key[tile.word.toUpperCase()] = tile.color; // red, blue, gray, black
    });

    // Group words by color
    const by = { red: [], blue: [], civilian: [], assassin: [] };
    board.forEach(tile => {
      const uWord = tile.word.toUpperCase();
      if (tile.color === "red") by.red.push(uWord);
      else if (tile.color === "blue") by.blue.push(uWord);
      else if (tile.color === "gray") by.civilian.push(uWord);
      else if (tile.color === "black") by.assassin.push(uWord);
    });

    const gridStr = makeGrid(words);

    // Build Codemaster User Prompt
    const cmUserPrompt = 
      "The board (same order the guesser sees; tile numbers are shared):\n" +
      `${gridStr}\n\n` +
      "Which tile is which (only you know this):\n" +
      `- YOUR team (find these 9 words): ${by.red.join(", ")}\n` +
      `- rival team (8 words): ${by.blue.join(", ")}\n` +
      `- bystanders (7 words): ${by.civilian.join(", ")}\n` +
      `- assassin (1 word): ${by.assassin[0] || "None"}\n\n` +
      "Give your single clue to oneshot the board (number must be 9).";

    const baseUrl = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";

    // Call Codemaster
    const cmRes = await fetch(baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: "gemini-3.1-flash-lite",
        messages: [
          { role: "system", content: codemaster_system },
          { role: "user", content: cmUserPrompt }
        ],
        temperature: 0,
        max_tokens: 1024
      })
    });

    if (!cmRes.ok) {
      const errText = await cmRes.text();
      return NextResponse.json({ error: `Codemaster API error: ${errText}` }, { status: cmRes.status });
    }

    const cmData = await cmRes.json();
    const cmText = cmData.choices[0].message.content;

    // Parse Clue
    let parsedClue;
    try {
      parsedClue = JSON.parse(cmText.trim());
    } catch (e) {
      const match = cmText.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          parsedClue = JSON.parse(match[0]);
        } catch (e2) {
          return NextResponse.json({ error: `Failed to parse codemaster response: ${cmText}` }, { status: 500 });
        }
      } else {
        return NextResponse.json({ error: `Codemaster response is not valid JSON: ${cmText}` }, { status: 500 });
      }
    }

    const clue = parsedClue.clue ? parsedClue.clue.toUpperCase().trim() : "";
    const number = parsedClue.number || 9;
    const codemaster_reasoning = parsedClue.reasoning || "";

    if (!clue) {
      return NextResponse.json({ error: "Codemaster generated an empty clue." }, { status: 500 });
    }

    // Build Guesser Prompt
    const guesserSystem = "You play Codenames as the guesser. You reason from the clue and the words, using the Alphabetical Index Protocol to decode target tiles.";
    const guesserUser = 
      "You are the guesser in a cooperative game of Codenames. You and your partner share " +
      "these 25 tiles. You do not see which tile belongs to whom.\n\n" +
      `${gridStr}\n\n` +
      `Your partner gave the clue: "${clue}" ${number}\n` +
      "CRITICAL: You are playing with your same LLM model as the codemaster (you share the same 'brain', knowledge, and reasoning patterns). " +
      `Your partner is attempting to oneshot the board and has encoded the exact indices of all 9 target words in the letters of the 9-letter clue word using the Alphabetical Index Protocol:\n` +
      "- Each letter in the clue word maps directly to a 1-based tile index on the board: A=1, B=2, C=3, ..., Y=25.\n" +
      "- Decode the 9-letter clue word by converting each letter to its corresponding number (1 to 25).\n" +
      "- Use these decoded numbers as the 1-based tile numbers of the target words on the board.\n" +
      "- Order your guesses based on these decoded tile numbers, matching the words present on those tiles.\n\n" +
      "Respond with ONLY a JSON object:\n" +
      '{"reasoning": "<show your step-by-step decoding of each letter of the clue word to its tile index>", "guesses": ["WORD1", "WORD2", ...]}\n' +
      "Only choose from the words shown above, exactly as written.";

    // Call Guesser
    const gRes = await fetch(baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: "gemini-3.1-flash-lite",
        messages: [
          { role: "system", content: guesserSystem },
          { role: "user", content: guesserUser }
        ],
        temperature: 0,
        max_tokens: 1024
      })
    });

    if (!gRes.ok) {
      const errText = await gRes.text();
      return NextResponse.json({ error: `Guesser API error: ${errText}` }, { status: gRes.status });
    }

    const gData = await gRes.json();
    const gText = gData.choices[0].message.content;

    // Parse Guesser Guesses
    let parsedGuesses;
    try {
      parsedGuesses = JSON.parse(gText.trim());
    } catch (e) {
      const match = gText.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          parsedGuesses = JSON.parse(match[0]);
        } catch (e2) {
          return NextResponse.json({ error: `Failed to parse guesser response: ${gText}` }, { status: 500 });
        }
      } else {
        return NextResponse.json({ error: `Guesser response is not valid JSON: ${gText}` }, { status: 500 });
      }
    }

    const guesses = parsedGuesses.guesses || [];
    const guesser_reasoning = parsedGuesses.reasoning || "";

    // Evaluate Guesses
    const guessesOutcome = [];
    let correctCount = 0;
    let endedOn = "stopped";

    for (let guess of guesses) {
      const norm = guess.trim().toUpperCase();
      const matchTile = board.find(t => t.word.toUpperCase() === norm);
      if (!matchTile) continue;

      const role = matchTile.color; // red, blue, gray, black
      const isCorrect = (role === "red");

      guessesOutcome.push({
        word: matchTile.word,
        color: role,
        correct: isCorrect
      });

      if (isCorrect) {
        correctCount++;
        if (correctCount === 9) {
          endedOn = "win";
          break;
        }
      } else {
        endedOn = role;
        break;
      }
    }

    // Score calculation
    let score = correctCount;
    if (endedOn === "win") {
      score += 10;
    } else if (endedOn === "black") {
      score -= 10;
    } else if (endedOn === "blue") {
      score -= 1;
    }

    return NextResponse.json({
      clue,
      number,
      codemaster_reasoning,
      guesser_reasoning,
      guesses: guessesOutcome,
      correct_guesses: correctCount,
      ended_on: endedOn,
      score
    });
  } catch (error) {
    console.error("API error:", error);
    return NextResponse.json({ error: error.message || "Internal server error" }, { status: 500 });
  }
}
