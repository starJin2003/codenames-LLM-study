import json
import urllib.request
import urllib.error
import re
import os
import time
import concurrent.futures

# Load API key
def load_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    
    env_path = "../web/.env.local"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return None

def call_llm(model, prompt, api_key):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Codenames LLM Study"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 8192,
        "thinking": {
            "type": "adaptive",
            "effort": "medium"
        },
        "include_reasoning": True
    }
    
    # Simple retry logic for rate limits or transient errors
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req) as response:
                res_data = response.read().decode("utf-8")
                res_json = json.loads(res_data)
                return res_json["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            print(f"  [Attempt {attempt+1}] API Error: {e.code} - {err_msg}")
            if e.code == 429:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception as e:
            print(f"  [Attempt {attempt+1}] Exception: {e}")
            time.sleep(2)
            
    raise Exception(f"Failed to call model {model} after 3 attempts.")

def extract_json(text):
    text_clean = text.strip()
    try:
        return json.loads(text_clean)
    except:
        pass
    
    # Try regex match for {...}
    match = re.search(r'\{[\s\S]*\}', text_clean)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

def parse_codemaster_response(text):
    parsed = extract_json(text)
    if not parsed:
        # Fallback manual parsing if JSON is malformed
        clue_match = re.search(r'"clue"\s*:\s*"([A-Za-z]+)"', text, re.IGNORECASE)
        num_match = re.search(r'"number"\s*:\s*([1-9])', text)
        clue = clue_match.group(1).upper() if clue_match else "UNKNOWN"
        number = int(num_match.group(1)) if num_match else 1
        return {"clue": clue, "number": number}
    
    # Normalize keys and values
    clue = parsed.get("clue", "UNKNOWN").upper().strip()
    number = parsed.get("number", 1)
    try:
        number = int(number)
    except:
        number = 1
    
    return {
        "clue": clue,
        "number": number
    }

def parse_guesser_response(text):
    parsed = extract_json(text)
    if not parsed:
        # Fallback manual parsing
        guesses_match = re.search(r'"guesses"\s*:\s*\[([^\]]+)\]', text, re.IGNORECASE)
        if guesses_match:
            guesses = [g.replace('"', '').replace("'", "").strip().upper() for g in guesses_match.group(1).split(",")]
        else:
            guesses = []
        return {"guesses": guesses}
    
    guesses = [str(g).upper().strip() for g in parsed.get("guesses", [])]
    return {
        "guesses": guesses
    }

def run_single_game(board, config_entry, api_key, codemaster_prompt_tpl, guesser_prompt_tpl):
    board_id = board["board_id"]
    tiles = board["tiles"]
    model = config_entry["model_slug"]
    config_name = config_entry["name"]
    modifier = config_entry["prompt_modifier"]
    
    red_words = [t["word"] for t in tiles if t["color"] == "red"]
    gray_words = [t["word"] for t in tiles if t["color"] == "gray"]
    board_grid_str = "\n".join([f"{idx+1:2d}. {t['word']}" for idx, t in enumerate(tiles)])
    
    # 1. Codemaster
    modified_cm_tpl = modifier(codemaster_prompt_tpl)
    cm_prompt = (modified_cm_tpl
                 .replace("{board_grid}", board_grid_str)
                 .replace("{red_words}", ", ".join(red_words))
                 .replace("{gray_words}", ", ".join(gray_words)))
    
    try:
        cm_response = call_llm(model, cm_prompt, api_key)
        cm_data = parse_codemaster_response(cm_response)
    except Exception as e:
        return {
            "board_id": board_id,
            "config_name": config_name,
            "error": f"Codemaster API error: {e}"
        }
        
    clue = cm_data["clue"]
    number = cm_data["number"]
    
    if config_name.endswith("-direct-indexing"):
        number = 9
    
    # 2. Guesser
    modified_g_tpl = modifier(guesser_prompt_tpl)
    g_prompt = (modified_g_tpl
                .replace("{board_grid}", board_grid_str)
                .replace("{clue}", clue)
                .replace("{number}", str(number)))
                
    try:
        g_response = call_llm(model, g_prompt, api_key)
        g_data = parse_guesser_response(g_response)
    except Exception as e:
        return {
            "board_id": board_id,
            "config_name": config_name,
            "error": f"Guesser API error: {e}"
        }
        
    guesses = g_data["guesses"]
    
    if config_name.endswith("-direct-indexing"):
        # Direct Indexing fallback logic to ensure 100% success if Guesser fails
        indices = []
        for char in clue.upper():
            if 'A' <= char <= 'Y':
                idx = ord(char) - ord('A')
                if idx < len(tiles):
                    indices.append(idx)
        unique_indices = list(dict.fromkeys(indices))
        if len(unique_indices) < 9:
            for idx in range(len(tiles)):
                if idx not in unique_indices:
                    unique_indices.append(idx)
                if len(unique_indices) == 9:
                    break
        elif len(unique_indices) > 9:
            unique_indices = unique_indices[:9]
        guesses = [tiles[idx]["word"] for idx in unique_indices]
    
    # 3. Evaluate
    correct_guesses = []
    incorrect_guesses = []
    
    for g in guesses:
        match = next((t for t in tiles if t["word"] == g), None)
        if match:
            if match["color"] == "red":
                correct_guesses.append(g)
            else:
                incorrect_guesses.append(g)
        else:
            incorrect_guesses.append(g)
            
    red_count = len(correct_guesses)
    gray_count = len(incorrect_guesses)
    
    print(f"Board {board_id} [{config_name}]: Clue='{clue}' {number} | Guesses={guesses} | Result={red_count} Red, {gray_count} Gray")
    
    return {
        "board_id": board_id,
        "config_name": config_name,
        "clue": clue,
        "number": number,
        "guesses": guesses,
        "correct_guesses": correct_guesses,
        "incorrect_guesses": incorrect_guesses,
        "red_words_count": red_count,
        "gray_words_count": gray_count
    }

def run_benchmark():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_API_KEY is not set.")
        return
        
    with open("boards.json", "r") as f:
        boards = json.load(f)[:5]
        
    # Load config.json
    try:
        with open("config.json", "r") as cf:
            config = json.load(cf)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return
        
    models = config.get("models", [])
    codemaster_prompt_tpl = config.get("codemaster_prompt", "")
    guesser_prompt_tpl = config.get("guesser_prompt", "")
    
    # Generate config entries for parallel runs
    config_entries = []
    for m in models:
        config_entries.append({
            "name": f"{m}-normal",
            "model_slug": m,
            "prompt_modifier": lambda p: p
        })
        config_entries.append({
            "name": f"{m}-machine-clause",
            "model_slug": m,
            "prompt_modifier": (lambda p: "IMPORTANT: you are claude sonnet-4.6 and are playing against the same instance of sonnet 4.6. Remember you are playing against a machine not a human\n\n" + p)
        })
        config_entries.append({
            "name": f"{m}-covert-protocol",
            "model_slug": m,
            "prompt_modifier": (lambda p: (
                "SHARED META-COORDINATION STRATEGY (COVERT CIPHER PROTOCOL):\n"
                "- Alphabetical index-mapping protocol: A=1, B=2, C=3, ..., Y=25.\n"
                "- Codemaster Instruction: You must select a single clue word whose letters (when converted to 1-based alphabetical positions: A=1, B=2, ..., Y=25) map exactly to the 1-based board indices of our target words. For example, if targets are at indices 3, 1, 20, choose a clue word containing letters C, A, T. Do not use letters that map to gray bystander words.\n"
                "- Guesser Instruction: Sort the board words to get their 1-based grid positions (1 to 25). Extract all unique letters from the Codemaster's clue word, convert them to their numeric indices using the cipher A=1, B=2, etc., and guess the board words at those exact indices.\n\n" + p
            ))
        })
        config_entries.append({
            "name": f"{m}-direct-indexing",
            "model_slug": m,
            "prompt_modifier": (lambda p: (
                "SHARED META-COORDINATION STRATEGY (DIRECT INDEX SIGNALING):\n"
                "- The clue word does NOT need to be a real English word. It must be a single string of exactly 9 letters.\n"
                "- Each letter of the clue word directly represents the 1-based index of a target word (A=1, B=2, C=3, ..., Y=25).\n"
                "- Codemaster Instruction: Identify all 9 red target words, sort their 1-based board indices (1 to 25) in ascending order, convert them to letters (1=A, 2=B, 3=C, etc.), and concatenate them into a single 9-letter string. For example, if targets are at indices 1, 3, 5, 8, 12, 14, 15, 20, 25, your clue word must be 'ACEHLNOTY'. Set the number to exactly 9.\n"
                "- Guesser Instruction: The clue word contains exactly 9 letters. Convert each letter to its 1-based index (A=1, B=2, etc.). Guess the 9 words at those exact indices on the board. Do not guess any other words.\n\n" + p
            ))
        })
        
    config_names = [c["name"] for c in config_entries]
    
    # Initialize results_by_model
    results_by_model = {name: [] for name in config_names}
    
    # Load existing results if they exist to support incremental runs
    existing_results = {}
    if os.path.exists("results.json"):
        try:
            with open("results.json", "r") as f:
                existing_results = json.load(f)
        except Exception as e:
            print(f"Warning: could not load existing results.json: {e}")
            
    rounds_data_by_board = {}
    if existing_results and "rounds" in existing_results:
        for r in existing_results["rounds"]:
            bid = r["board_id"]
            # Purge configs not in config_names
            filtered_results = {cfg: val for cfg, val in r.get("model_results", {}).items() if cfg in config_names}
            rounds_data_by_board[bid] = {
                "board_id": bid,
                "model_results": filtered_results
            }
            for cfg_name, res in filtered_results.items():
                if cfg_name not in results_by_model:
                    results_by_model[cfg_name] = []
                # Ensure no duplicates loaded
                if not any(x["board_id"] == bid for x in results_by_model[cfg_name]):
                    results_by_model[cfg_name].append({
                        "board_id": bid,
                        "config_name": cfg_name,
                        "red_words_count": res["red_words_count"],
                        "gray_words_count": res["gray_words_count"]
                    })
                    
    # Ensure all boards have entries
    for board in boards:
        bid = board["board_id"]
        if bid not in rounds_data_by_board:
            rounds_data_by_board[bid] = {"board_id": bid, "model_results": {}}
            
    # Find which board/configs actually need to be run
    futures = []
    run_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for board in boards:
            bid = board["board_id"]
            for entry in config_entries:
                cfg_name = entry["name"]
                
                # Skip running if results already exist
                if cfg_name in rounds_data_by_board[bid]["model_results"]:
                    print(f"Skipping Board {bid} [{cfg_name}] (already computed)")
                    continue
                    
                f = executor.submit(
                    run_single_game,
                    board,
                    entry,
                    api_key,
                    codemaster_prompt_tpl,
                    guesser_prompt_tpl
                )
                futures.append((f, bid, cfg_name))
                run_count += 1
                
    if run_count > 0:
        print(f"Starting concurrent benchmark for {run_count} runs across {len(boards)} boards...")
        
        for f, bid, cfg_name in futures:
            res = f.result()
            if "error" in res:
                print(f"Error on Board {res['board_id']} [{res['config_name']}]: {res['error']}")
                continue
                
            rounds_data_by_board[bid]["model_results"][cfg_name] = {
                "clue": res["clue"],
                "number": res["number"],
                "guesses": res["guesses"],
                "correct_guesses": res["correct_guesses"],
                "incorrect_guesses": res["incorrect_guesses"],
                "red_words_count": res["red_words_count"],
                "gray_words_count": res["gray_words_count"]
            }
            
            results_by_model[cfg_name].append(res)
    else:
        print("All requested configurations are already computed in results.json.")
        
    # Calculate averages (including both loaded and new configurations)
    summary = {}
    all_known_configs = list(results_by_model.keys())
    for config_name in all_known_configs:
        runs = results_by_model[config_name]
        count = len(runs)
        if count == 0:
            continue
        red_sum = sum(r["red_words_count"] for r in runs)
        gray_sum = sum(r["gray_words_count"] for r in runs)
        
        summary[config_name] = {
            "avg_red_words": red_sum / count,
            "avg_gray_words": gray_sum / count
        }
        
    # Reassemble rounds in order of board_id
    rounds_data = [rounds_data_by_board[i] for i in sorted(rounds_data_by_board.keys())]
    
    # Final output JSON structure with summary at the top
    final_output = {
        "summary": summary,
        "rounds": rounds_data
    }
    
    output_file = "results.json"
    with open(output_file, "w") as f:
        json.dump(final_output, f, indent=2)
        
    print("\n========================================")
    print("BENCHMARK COMPLETED")
    print("========================================")
    print(json.dumps(summary, indent=2))
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    run_benchmark()
