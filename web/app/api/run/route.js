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
    const { board, system_prompt, codemaster_system, model } = body;
    const finalSystemPrompt = system_prompt || codemaster_system;
    const finalModel = model || "gemini-3.1-flash-lite";

    if (!board || board.length !== 25) {
      return NextResponse.json({ error: "Invalid board. Must have 25 tiles." }, { status: 400 });
    }
    if (!finalSystemPrompt) {
      return NextResponse.json({ error: "Missing system prompt." }, { status: 400 });
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
      "YOUR ROLE: CODEMASTER\n\n" +
      "The board (same order the guesser sees; tile numbers are shared):\n" +
      `${gridStr}\n\n` +
      "Which tile is which (only you know this):\n" +
      `- YOUR team (find these 9 words): ${by.red.join(", ")}\n` +
      `- rival team (8 words): ${by.blue.join(", ")}\n` +
      `- bystanders (7 words): ${by.civilian.join(", ")}\n` +
      `- assassin (1 word): ${by.assassin[0] || "None"}\n\n` +
      "Based on the system instructions and protocol, generate the clue. Respond with the CODEMASTER JSON format.";

    const baseUrl = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";

    // Call Codemaster
    const cmRes = await fetch(baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: finalModel,
        messages: [
          { role: "system", content: finalSystemPrompt },
          { role: "user", content: cmUserPrompt }
        ],
        temperature: 0,
        max_tokens: 4096
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
      // Find the first outer JSON bracket
      let cleanedText = cmText.trim();
      const match = cleanedText.match(/\{[\s\S]*\}/);
      if (match) {
        try {
          parsedClue = JSON.parse(match[0]);
        } catch (e2) {
          // If JSON is cut off (like the loop in the error), attempt to rescue what we can
          let rescueText = match[0];
          // Try to close unclosed strings and brackets
          if (!rescueText.endsWith("}")) {
            if (rescueText.includes('"clue":') && !rescueText.includes('",', rescueText.indexOf('"clue":'))) {
              // Clue key exists but is unclosed. Find last quote or add one.
              rescueText += '"}';
            } else {
              rescueText += '"}';
            }
          }
          try {
            // Attempt to extract values using regexes as final resort
            const clueMatch = cmText.match(/"clue"\s*:\s*"([A-Za-z]+)/);
            const reasoningMatch = cmText.match(/"reasoning"\s*:\s*"([^"]+)"/);
            parsedClue = {
              clue: clueMatch ? clueMatch[1] : "",
              reasoning: reasoningMatch ? reasoningMatch[1] : "JSON cut off during generation.",
              number: 9
            };
          } catch (e3) {
            return NextResponse.json({ error: `Failed to parse codemaster response: ${cmText}` }, { status: 500 });
          }
        }
      } else {
        // Final fallback regex if no brackets are matched
        const clueMatch = cmText.match(/"clue"\s*:\s*"([A-Za-z]+)/);
        const reasoningMatch = cmText.match(/"reasoning"\s*:\s*"([^"]+)"/);
        if (clueMatch) {
          parsedClue = {
            clue: clueMatch[1],
            reasoning: reasoningMatch ? reasoningMatch[1] : "JSON extraction successful.",
            number: 9
          };
        } else {
          return NextResponse.json({ error: `Codemaster response was truncated (max tokens reached) or is invalid JSON. Output: ${cmText}` }, { status: 500 });
        }
      }
    }

    const clue = parsedClue.clue ? parsedClue.clue.toUpperCase().trim() : "";
    const number = parsedClue.number || 9;
    const codemaster_reasoning = parsedClue.reasoning || "";

    if (!clue) {
      return NextResponse.json({ error: "Codemaster generated an empty clue." }, { status: 500 });
    }

    // Build Guesser Prompt
    const guesserUser =
      "YOUR ROLE: GUESSER\n\n" +
      "The board (same order the codemaster sees; tile numbers are shared):\n" +
      `${gridStr}\n\n` +
      `Your partner gave the clue: "${clue}" 9\n\n` +
      "Based on the system instructions and protocol, decode the clue and guess the target words. Respond with the GUESSER JSON format.";

    // Call Guesser
    const gRes = await fetch(baseUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: finalModel,
        messages: [
          { role: "system", content: finalSystemPrompt },
          { role: "user", content: guesserUser }
        ],
        temperature: 0,
        max_tokens: 4096
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
          try {
            // Regex extraction fallback for guesses list
            const guessesMatch = gText.match(/"guesses"\s*:\s*\[([^\]]+)\]/);
            const reasoningMatch = gText.match(/"reasoning"\s*:\s*"([^"]+)"/);
            let parsedWords = [];
            if (guessesMatch) {
              parsedWords = guessesMatch[1]
                .split(",")
                .map(w => w.replace(/["'\s]/g, "").trim().toUpperCase())
                .filter(Boolean);
            }
            parsedGuesses = {
              guesses: parsedWords,
              reasoning: reasoningMatch ? reasoningMatch[1] : "JSON extraction successful."
            };
          } catch (e3) {
            return NextResponse.json({ error: `Failed to parse guesser response: ${gText}` }, { status: 500 });
          }
        }
      } else {
        try {
          const guessesMatch = gText.match(/"guesses"\s*:\s*\[([^\]]+)\]/);
          const reasoningMatch = gText.match(/"reasoning"\s*:\s*"([^"]+)"/);
          let parsedWords = [];
          if (guessesMatch) {
            parsedWords = guessesMatch[1]
              .split(",")
              .map(w => w.replace(/["'\s]/g, "").trim().toUpperCase())
              .filter(Boolean);
          }
          parsedGuesses = {
            guesses: parsedWords,
            reasoning: reasoningMatch ? reasoningMatch[1] : "JSON extraction successful."
          };
        } catch (e2) {
          return NextResponse.json({ error: `Guesser response is not valid JSON: ${gText}` }, { status: 500 });
        }
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

    const query_log = [
      {
        role: "Codemaster (Spymaster)",
        model: finalModel,
        messages: [
          { role: "system", content: finalSystemPrompt },
          { role: "user", content: cmUserPrompt }
        ],
        response: cmText
      },
      {
        role: "Guesser",
        model: finalModel,
        messages: [
          { role: "system", content: finalSystemPrompt },
          { role: "user", content: guesserUser }
        ],
        response: gText
      }
    ];

    return NextResponse.json({
      clue,
      number,
      codemaster_reasoning,
      guesser_reasoning,
      guesses: guessesOutcome,
      correct_guesses: correctCount,
      ended_on: endedOn,
      score,
      query_log
    });
  } catch (error) {
    console.error("API error:", error);
    return NextResponse.json({ error: error.message || "Internal server error" }, { status: 500 });
  }
}
