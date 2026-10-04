# Model-authoring pilot: verbatim examples

Each example names the recorded history it came from, the run directory and
call number under `runs/`, and the first 12 hex digits of the SHA-256 of the
exact raw response (`runs/<run>/responses/<sha256>.txt`). The texts are
reproduced byte for byte from those files. For curios, "player sees" is the
native output at the admission context (the history's sanity and insight,
3 charges, state 0).

Choice: examples were picked by hand to show the range, including the plain
and the striking. They are not a random sample; `summary.json` has the
aggregates.

### curio

**bard-00007**, layer `abbott` — `runs/pilot` call 1, response `07dce66f99bf`, 171 s, admitted

Player sees: name **Late-Join Mitre**; inspect (start of game): “A palm brass mitre. Both inner edges meet, yet the join is a breath late.”; first use: “You set the long arm flat. The short arm meets late by less than a shaving.” (requested Sanity -1).

Continuity note: “A palm-sized brass mitre whose inner corner joins a breath late. Alignment, turn, and press change the reading with sanity, insight, charges, and prior state, always on the metal and inside a limited frame. Proposal summary only: not a placement, not a sighting.”

<details><summary>Lua source (3993 bytes)</summary>

```lua
local function inspect(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  if c == 0 and st == 0 then
    return 'The mitre offers no fresh reading. Its corner holds a flat, unproved right angle.'
  end
  if c == 0 then
    return 'No fresh reading offers. The mitre keeps its last flat alignment, unfinished.'
  end
  if st == 0 then
    if s >= 90 then
      return 'A palm brass mitre. Both inner edges meet, yet the join is a breath late.'
    elseif s >= 50 then
      return 'A palm brass mitre. Turned in the hand, one arm outruns the other by a hair.'
    else
      return 'A palm brass mitre. The corner gap shifts if the eye moves, not the brass.'
    end
  end
  if st == 1 then
    if i == 0 then
      return 'The long arm lies flat. The short arm meets it beside the proof, not as one.'
    else
      return 'The long arm lies flat. Counted edges keep the late join on the brass alone.'
    end
  end
  if st == 2 then
    if s >= 50 then
      return 'Turned once, the inner edge leaves a line too thin to call a shadow.'
    else
      return 'Turned once, the thin line seems raised, yet a nail finds only brass.'
    end
  end
  if st < 8 then
    if c == 1 then
      return 'The inner edge has dulled. Pressed flat, a bright seam stays short of closing.'
    elseif s >= 70 then
      return 'Pressed flat, the corner almost closes. A bright seam stays narrower than breath.'
    else
      return 'Pressed flat, the seam widens when you blink and narrows when you do not.'
    end
  end
  if c == 1 then
    return 'The inner edge has dulled. Often read, it still ends a hair before the join.'
  end
  return 'Often read, each edge ends where the palm expects a join, then falls short.'
end

local function apply(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  if c == 0 then
    return {
      text = 'The mitre does not take the press. Its corner stays as it was.',
      state = st,
      sanity_delta = 0
    }
  end
  if st == 0 then
    if s >= 80 then
      return {
        text = 'You set the long arm flat. The short arm meets late by less than a shaving.',
        state = 1,
        sanity_delta = -1
      }
    end
    return {
      text = 'You set the long arm flat. The late join was already plain, and does not deepen.',
      state = 1,
      sanity_delta = 0
    }
  end
  if st == 1 then
    if i == 0 then
      return {
        text = 'You turn the mitre. Uncounted, the gap reads only as a fault in the brass.',
        state = 2,
        sanity_delta = -1
      }
    end
    return {
      text = 'You turn the mitre. A count keeps the gap on the metal, local and finite.',
      state = 2,
      sanity_delta = 0
    }
  end
  if st == 2 then
    if s < 40 then
      return {
        text = 'You press the corner shut. The finite seam is plainer than the dread; you steady.',
        state = 3,
        sanity_delta = 1
      }
    end
    return {
      text = 'You press the corner shut. A bright seam remains; the surface feels a little thin.',
      state = 3,
      sanity_delta = -1
    }
  end
  local nst = st
  if st < 255 then
    nst = st + 1
  end
  if s < 50 then
    if i == 0 then
      return {
        text = 'Another press. The bounded corner is plainer than the dread, and you ease a little.',
        state = nst,
        sanity_delta = 1
      }
    end
    return {
      text = 'Another press. A count makes the corner finite again, and you ease a little.',
      state = nst,
      sanity_delta = 1
    }
  end
  if i == 0 then
    return {
      text = 'Another press. The angle disagrees, then agrees, still within a hair of true.',
      state = nst,
      sanity_delta = 0
    }
  end
  return {
    text = 'Another press. Counted again, the two edges still miss by the same short hair.',
    state = nst,
    sanity_delta = 0
  }
end

return {
  name = 'Late-Join Mitre',
  inspect = inspect,
  apply = apply
}
```

</details>

**bard-default-path-00023**, layer `poe` — `runs/pilot` call 39, response `4436f805bb92`, 160 s, admitted

Player sees: name **Warped Pitch-Pipe**; inspect (start of game): “A dented brass pitch-pipe. Cold metal, and a bore that smells faintly of borrowed breath.”; first use: “A thin note leaves the pipe, flat by a hair. The flatness lingers in the teeth longer than the sound.” (requested Sanity -1).

Continuity note: “A warped brass pitch-pipe. One dent and one slightly flat note gather pressure under repeated attention, shifting with sanity, insight, charges, and prior state. A steadier misreading can briefly ease the discrepancy before it returns. No quest or hidden fact is claimed.”

<details><summary>Lua source (2809 bytes)</summary>

```lua
return {
name='Warped Pitch-Pipe',
inspect=function(ctx)
local s=ctx.state
local san=ctx.sanity
local ins=ctx.insight
local ch=ctx.charges
if ch==0 then
return 'The pipe is mute in your hand. The dent remains, as if still waiting for a breath you will not give.'
elseif san<40 then
return 'The dent keeps the shape of a listening mouth. You are not sure the pipe was made that way.'
elseif ins>500 and s>=1 then
return 'You hear no note, yet the silence after looking seems pitched a little flat of true.'
elseif ch==1 and s>=1 then
return 'The brass looks thinner at the lip, though you cannot say what was worn away.'
elseif s==0 and san>=80 then
return 'A dented brass pitch-pipe. Cold metal, and a bore that smells faintly of borrowed breath.'
elseif s==0 then
return 'The pitch-pipe is warm where you did not hold it. The dent at the lip looks older than the brass.'
elseif s>=4 then
return 'Each glance finds the same dull brass, and each time the dullness seems nearer to your pulse.'
else
return 'A small discrepancy: the lip is smooth, but your thumb remembers a burr that is no longer there.'
end
end,
apply=function(ctx)
local s=ctx.state
local san=ctx.sanity
local ins=ctx.insight
local ch=ctx.charges
local next_state=s
local delta=0
local text
if ch==0 then
text='You raise the pipe and lower it. No breath passes. The dent watches the space you did not fill.'
else
if s<255 then next_state=s+1 end
if s==0 and san>=70 then
delta=-1
text='A thin note leaves the pipe, flat by a hair. The flatness lingers in the teeth longer than the sound.'
elseif s==0 then
delta=-1
text='The note is almost true. Almost. You cannot name which edge of the tone has gone missing.'
elseif ins>=400 then
delta=-2
text='You blow, and the flat note seems to answer a breath you have not yet taken. The brass stays cold.'
elseif san<30 then
delta=-2
text='The pipe gives a clean tone. You distrust it. Clean feels like a correction aimed at your mouth.'
elseif s==2 and san>=55 then
delta=1
text='You match the flatness on purpose. For a moment the dent is only a dent, and the metal only metal.'
elseif ch==1 and s<5 then
delta=-1
text='A short breath, a shorter note. The flatness stays on the lip after the brass has cooled.'
elseif s>=12 then
delta=-2
text='You know the flatness before you blow. Knowing it does not keep it from settling in the teeth.'
elseif s>=5 and san<60 then
delta=-2
text='The same thin flatness. It should have dulled by now. Instead it seems to count each attempt.'
elseif s>=5 then
delta=-1
text='The same thin flatness. Repetition should dull it. Instead the note seems to number your breaths.'
else
delta=-1
text='Breath fogs the lip and clears at once. The note is flat again, as if the pipe preferred the error.'
end
end
return {text=text,state=next_state,sanity_delta=delta}
end
}
```

</details>

**wizard-default-path-00007**, layer `abbott` — `runs/pilot` call 49, response `59495c12982d`, 137 s, admitted

Player sees: name **fourth corner**; inspect (start of game): “A thin brass square, palm-sized. Three corners sit flush. The fourth does not.”; first use: “You seat three corners. The fourth rises by a margin too even to be a dent.” (requested Sanity +0).

Continuity note: “A palm-sized brass square with one corner that will not sit flush. Inspection and use keep finding the same exact margin, and the wording shifts with attention, clarity, and steadiness while remaining inside a bounded frame of reference. The discrepancy is not explained, and no further place is opened or promised.”

<details><summary>Lua source (2308 bytes)</summary>

```lua
return {name='fourth corner',inspect=function(ctx) local st=ctx.state; local s=ctx.sanity; local i=ctx.insight; if st==0 then return 'A thin brass square, palm-sized. Three corners sit flush. The fourth does not.' elseif st==1 then return 'Outline unchanged. The lifted corner is familiar now, and no less wrong.' elseif i>500 then return 'Four equal edges. The gap is regular. Regularity here is not a reason.' elseif s<50 then return 'The square looks honest. The flatness of the room seems the less reliable measure.' elseif st<8 then if ctx.charges==0 then return 'The square rests. The corner holds one margin, and will not add another.' end return 'You have pressed it. The rise is the same height, to the limit of touch.' else return 'It remains a square. The unseated corner is a fact with no side to own it.' end end,apply=function(ctx) local st=ctx.state; local s=ctx.sanity; local i=ctx.insight; local c=ctx.charges; local ns=st; if st<255 then ns=st+1 end; local text; local delta; if st==0 then if s<50 then text='The brass is true in the hand. On the desk, one corner will not agree.'; delta=-1 else text='You seat three corners. The fourth rises by a margin too even to be a dent.'; delta=0 end elseif st==1 then if i>0 then text='The repeat is exact. Finer notice does not find a nick to explain it.'; delta=-1 else text='A second press repeats the rise exactly. Wear would have wandered.'; delta=-1 end elseif st==2 then if s<50 then text='Turned once, it is equal on every side, and still unfit for the plane.'; delta=-2 else text='You turn it. Each side is equal. The lift belongs to none of them.'; delta=-1 end elseif s<30 then text='You count four sides. The count holds. The lift stays outside the count.'; delta=1 elseif i>500 then text='Clearer sight cleans the margin. It does not supply the missing close.'; delta=0 elseif i==0 and st<6 then text='You try to name the error. The name needs a direction you do not have.'; delta=-1 elseif s<50 then text='Flat in the fingers, not flat on the wood. You cannot keep both.'; delta=-2 elseif c==1 then text='The brass is cold and exact. This press adds no new height to the corner.'; delta=-1 else text='You set it down. The corner keeps its small, precise disobedience.'; delta=0 end; return {text=text,state=ns,sanity_delta=delta} end}
```

</details>

**broad-restore-capture**, layer `hodgson` — `runs/pilot` call 61, response `7eed56b96bb0`, 137 s, admitted

Player sees: name **Frayed Sounding Plummet**; inspect (start of game): “A palm-sized sounding lead, salt in the seam. The cord is no longer than your hand.”; first use: “You turn the plummet. One face is colder, and the cord's shadow falls a finger long.” (requested Sanity -1).

Continuity note: “A palm-sized salt-crusted sounding lead with a hand-short cord. Wear and a pale groove suggest a drop of uncertain scale, never a passage or pursuer. Inspect only reports the discrepancy; apply advances a wear-state and a small sanity delta from sanity, insight, charges, and state, then repetition flattens the unease.”

<details><summary>Lua source (2756 bytes)</summary>

```lua
return {
  name = "Frayed Sounding Plummet",
  inspect = function(ctx)
    local s = ctx.state
    local n = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    if c == 0 then
      return "The plummet sits mute. Its cord end is squared, as if the last strand already left."
    end
    if s == 0 then
      if n < 50 then
        return "Salt cakes a palm-sized lead. In the dim of your hand the short cord feels oddly far."
      end
      return "A palm-sized sounding lead, salt in the seam. The cord is no longer than your hand."
    end
    if s < 4 then
      if i > 500 then
        return "A scratched mark on the lead begins like a numeral and ends as a tide-line, unfinished."
      end
      return "The cord is unchanged. A pale groove in the lead runs deeper than a thumb could press."
    end
    if n < 30 then
      return "The weight has not grown. Yet the groove slips past the rim your eyes can settle on."
    end
    return "Same small lead, same short cord. The wear suggests a drop you cannot measure here."
  end,
  apply = function(ctx)
    local s = ctx.state
    local n = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local ns = s + 1
    if ns > 255 then
      ns = 255
    end
    if c == 0 then
      return { text = "No strand answers. The salt-seam stays shut, and the small lead keeps its own weight.", state = s, sanity_delta = 0 }
    end
    if s == 0 then
      return { text = "You turn the plummet. One face is colder, and the cord's shadow falls a finger long.", state = ns, sanity_delta = -1 }
    end
    if c == 1 then
      return { text = "The last bright bite in the lead has dulled. Salt remains; the groove does not close.", state = ns, sanity_delta = -1 }
    end
    if s < 4 then
      return { text = "The groove under your nail is longer than last time. The lead itself is not.", state = ns, sanity_delta = -1 }
    end
    if s < 9 and n >= 70 then
      return { text = "Distance gathers in the scratch: a long drop, held in a weight that still fits the palm.", state = ns, sanity_delta = -2 }
    end
    if s < 9 and i > 200 then
      return { text = "You try to read the scratch as measure. It refuses a last digit and stays only wear.", state = ns, sanity_delta = -1 }
    end
    if s < 9 then
      return { text = "The plummet ticks once against your knuckle, light as tin, then heavy as a deep line.", state = ns, sanity_delta = -1 }
    end
    if n < 40 then
      return { text = "It is only lead and salt. The farness remains, but it no longer asks to be believed.", state = ns, sanity_delta = 1 }
    end
    return { text = "Again the short cord. Again a wear-mark scaled for water you are not standing in.", state = ns, sanity_delta = 0 }
  end
}
```

</details>

### curio_history

**wizard-default-path-00023**, layer `carroll` — `runs/pilot` call 70, response `2acd79cc8b66`, 129 s, admitted

Player sees: name **Contrary Teaspoon**; inspect (start of game): “The teaspoon is empty. Still, a thin waterline waits above the metal, as if fullness were a facing.”; first use: “You turn it. The waterline stays. Only the word empty departs, and full comes to stand there.” (requested Sanity -1).

Continuity note: “A contrary teaspoon whose empty and full names trade places when turned, while a waterline stays put. Inspection states the mismatch; use reverses the sentence and returns a small sanity delta bounded by facing, sanity, and charges. Insight only sharpens wording. Supplied fountain refresh and wizard role are motifs, not events the spoon witnesses or completes.”

<details><summary>Lua source (3885 bytes)</summary>

```lua
return {
  name = "Contrary Teaspoon",
  inspect = function(ctx)
    local turned = (ctx.state % 2) == 1
    if ctx.charges == 0 then
      if turned then
        return "Finished, and facing full. The bowl is bare. Both statements remain, with no turn left between them."
      end
      return "Finished, and facing empty. A waterline still hovers, though nothing remains that could be turned."
    end
    if turned then
      if ctx.sanity <= 25 then
        return "It says full. The bowl is bare. At this pitch the disagreement sounds like good order."
      elseif ctx.insight > 500 then
        return "Marked full. Contents: none. The mark is correct only if correct has been allowed to face backward."
      elseif ctx.insight > 0 then
        return "It reads full. No water is present. Exactness is the part that refuses to settle."
      end
      return "The teaspoon calls itself full. You see no water. One sentence is facing the wrong way."
    end
    if ctx.charges == 1 then
      return "Empty, with one turn left. The waterline above the bowl already behaves as if that turn were done."
    end
    if ctx.sanity <= 25 then
      return "Empty, officially. The missing sip has a cleaner edge than the metal, and that seems sufficient."
    elseif ctx.insight > 500 then
      return "Empty by the mark. A waterline stands above the bowl. Consistency holds only if direction is optional."
    elseif ctx.insight > 0 then
      return "Empty by the mark, yet a waterline stands over the metal. The error is precise enough to distrust."
    end
    return "The teaspoon is empty. Still, a thin waterline waits above the metal, as if fullness were a facing."
  end,
  apply = function(ctx)
    if ctx.charges == 0 then
      return {
        text = "It will not turn. Empty and full keep the facing they already have.",
        state = ctx.state,
        sanity_delta = 0
      }
    end
    local next_state = ctx.state + 1
    if next_state > 255 then
      next_state = 0
    end
    local turned = (ctx.state % 2) == 1
    local delta = 0
    if ctx.sanity >= 90 then
      delta = -1
    elseif ctx.sanity <= 25 then
      delta = 1
    end
    if ctx.charges == 1 and delta > -2 then
      delta = delta - 1
    end
    if delta < -2 then
      delta = -2
    end
    if delta > 2 then
      delta = 2
    end
    local text
    if ctx.charges == 1 then
      if turned then
        text = "You turn it back, and this is the last turn. Full gives up its name; empty keeps it, too firmly."
      else
        text = "You turn it once. No later turn remains to argue. The empty bowl accepts the name of full."
      end
    elseif turned then
      if ctx.sanity <= 25 then
        text = "You turn it back. Empty fits so neatly that the neatness seems to have arrived first."
      elseif ctx.insight > 500 then
        text = "You turn it back. The names trade exactly. Exact trade is a kind of proof, and the proof will not sit still."
      elseif ctx.insight > 0 then
        text = "You turn it back. Full yields its name to empty. The exchange balances, and balance is the worry."
      else
        text = "You turn it back. What was called full is empty again, and the again is the unsteady part."
      end
    elseif ctx.sanity <= 25 then
      text = "You turn it. Wrong-way full feels like the instruction you already meant. The bowl stays dry."
    elseif ctx.insight > 500 then
      text = "You turn the spoon. The count reverses before any water can object. There is no water to object."
    elseif ctx.insight > 0 then
      text = "You turn the spoon. Nothing spills; nothing was held. The measurement reverses without a spill to prove it."
    else
      text = "You turn it. The waterline stays. Only the word empty departs, and full comes to stand there."
    end
    return { text = text, state = next_state, sanity_delta = delta }
  end
}
```

</details>

**madman-00023**, layer `carroll` — `runs/pilot` call 86, response `71a9d5a445dc`, 183 s, admitted

Player sees: name **The Recanting Card**; inspect (start of game): “A cream card. This face says the other is blank. This face is not.”; first use: “You turn it. The sentence you believed is now the one printed against the table.” (requested Sanity -1).

Continuity note: “A cream calling card whose rule denies the face being read. Inspection and use answer by sanity, insight, charges, and a short state cycle: each use reverses the denial and shifts sanity by one in opposite directions above and below fifty, or by none above five hundred insight. The reversal rhymes with retraced steps in the supplied history without treating that history as the card's knowledge or as a future event.”

<details><summary>Lua source (2723 bytes)</summary>

```lua
return { name = 'The Recanting Card', inspect = function(ctx) local s = ctx.sanity local i = ctx.insight local c = ctx.charges local t = ctx.state if c == 0 then if s >= 50 then return 'Both faces lie up, which the card calls impossible, and therefore finished.' end return 'The card is face-down and face-up together. Your hand cannot decide which is rude.' end if t == 0 then if i == 0 and s >= 50 then return 'A cream card. This face says the other is blank. This face is not.' elseif i == 0 then return 'The card is warm, as if just pocketed. Its rule says it has not been held.' elseif i > 500 then return 'Unread, the rule is already older than the card, which the rule does not permit.' end return 'The ink is newer than the crease. The sentence denies the crease exists.' end if t < 4 then if s >= 50 then return 'Turned, it now says you have not turned it. The dog-ear covers the proof.' end return 'The turn feels repeated. The card agrees you have not done it, so you have.' end if i > 500 then return 'The rule is older than the card that carries it, which the rule does not allow.' elseif s < 50 then return 'Smaller print, same denial. The impossibility is familiar, and the paper is not.' end return 'The same rule, smaller. It agrees with itself only by disagreeing twice.' end, apply = function(ctx) local s = ctx.sanity local i = ctx.insight local c = ctx.charges local t = ctx.state local nxt = t + 1 if nxt > 6 then nxt = 0 end local delta = 0 if i <= 500 then if s >= 50 then if t % 2 == 0 then delta = -1 else delta = 1 end else if t % 2 == 0 then delta = 1 else delta = -1 end end end local text if i > 500 then if c <= 1 then text = 'The rule closes on itself and leaves the air unchanged. Blank and not blank remain equally true.' else text = 'The contradiction is exact and does not stir the air. The card seems to have expected that.' end elseif c <= 1 and s >= 50 then text = 'The sentence pinches shut. What you read is now the side against the table.' elseif c <= 1 then text = 'It fails to finish, and the failure fits. The blank side keeps its letters.' elseif i == 0 and t == 0 then text = 'You turn it. The sentence you believed is now the one printed against the table.' elseif i == 0 and s >= 50 then text = 'It recants. What was blank is lettered, and what was lettered claims to be blank.' elseif i == 0 then text = 'You turn it the wrong way, which is the way it asked. The warmth stays in the paper.' elseif t % 2 == 0 then text = 'The rule reverses under your thumb. The corner you folded unfolds on the other face.' else text = 'Set down, it faces up as the side you did not choose. The choice remains on record.' end return { text = text, state = nxt, sanity_delta = delta } end }
```

</details>

**wizard-default-path-00041**, layer `wilde` — `runs/pilot` call 76, response `9080b98d63d0`, 194 s, admitted

Player sees: name **visiting-card case**; inspect (start of game): “A visiting-card case, gilt, suited to a wizard. The lid is kinder than any honest mirror.”; first use: “You open it. The lid improves you by one courtesy. You almost thank an object for the favor.” (requested Sanity +0).

Continuity note: “Original gilt visiting-card case: a social mirror that improves the face by one courtesy, then repeats it until the courtesy resembles a debt. Lines vary with sanity, insight, charges, and prior openings. A reluctant hinge and a late strange note lightly echo recorded door-reluctance and strange whistling, without causes, companions, placement, or later events.”

<details><summary>Lua source (3225 bytes)</summary>

```lua
local function inspect(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  if st >= 4 and s < 50 then
    return 'The gilt still flatters. You do not. The lid offers a face that has stopped consulting you.'
  end
  if st >= 8 and st < 40 then
    return 'You refused the correction. The gilt remembers the better version and does not argue. Yet.'
  end
  if i >= 100 then
    return 'The glass is late by a blink. Gilt does not delay. The lid is composing a better introduction.'
  end
  if c == 0 then
    return 'The case is shut for good. A last courtesy remains in the gilt, unpaid and unreturned.'
  end
  if st == 0 and s >= 80 then
    return 'A visiting-card case, gilt, suited to a wizard. The lid is kinder than any honest mirror.'
  end
  if st == 0 then
    return 'A gilt card-case. The mirror-lid corrects your mouth before you have decided to smile.'
  end
  if c == 1 then
    return 'One sitting of polish remains. The hinge is reluctant to close on a face it has improved.'
  end
  if i == 0 and s >= 50 then
    return 'Warm gilt, cold glass. The improvement is precise, social, and not quite your own.'
  end
  return 'The case keeps its manners. Your reflection keeps a smile you do not remember agreeing to.'
end

local function apply(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  local ns = st + 1
  if ns > 255 then ns = 255 end
  local text = 'You accept the prettier mouth. The case clicks shut, satisfied, as if the introduction went well.'
  local delta = 0
  if i >= 200 and s >= 40 then
    text = 'You decline the edit. The glass finishes the smile anyway, a moment after you have looked away.'
    delta = 0
    if st >= 3 then delta = 1 end
    if st < 8 then ns = 8 end
  elseif s < 40 then
    text = 'The gilt is calm. You are not. It lends you a face and records the debt in your own features.'
    delta = -2
  elseif s >= 85 and st == 0 then
    text = 'You open it. The lid improves you by one courtesy. You almost thank an object for the favor.'
    delta = 1
    if s >= 100 then delta = 0 end
  elseif st >= 8 then
    text = 'The case has kept the version you refused. Opening it now is only a visit to an old vanity.'
    delta = 0
    if s < 70 then delta = -1 end
  elseif c <= 1 and st >= 1 then
    text = 'Little polish remains. The clasp answers late, as a strange note would, and keeps the better pose.'
    delta = -1
  elseif st >= 1 and st < 8 then
    text = 'The second arrangement matches the first. A repeated compliment is how a lie stays beautiful.'
    delta = -1
    if s < 70 then delta = -2 end
  elseif i > 0 then
    text = 'A faint wrongness: the reflection inhales after you do. Taste notices. Certainty does not.'
    delta = -1
  else
    delta = 1
    if st >= 2 then delta = -1 end
  end
  if st >= 12 and s < 55 then
    text = 'It has learned your best angle. You have not learned its price. The hinge waits, polite.'
    delta = -2
  end
  if delta > 2 then delta = 2 end
  if delta < -2 then delta = -2 end
  return { text = text, state = ns, sanity_delta = delta }
end

return { name = 'visiting-card case', inspect = inspect, apply = apply }
```

</details>

**bard-inherited-00023**, layer `mackay` — `runs/pilot` call 90, response `ed5ad9acdd8a`, 139 s, admitted

Player sees: name **Concord Reed**; inspect (start of game): “A thumb-dark reed, split at the lip. Ink on the grain says ALL AGREE. The hand was sure; the wood is not.”; first use: “You set the reed to your lip. It scrapes high and thin, not the agreed note. The miss is small, and hard to leave alone.” (requested Sanity -1).

Continuity note: “Split reed inked ALL AGREE. A thin high scrape set against a confident claim, after Mackay's interest in credulity, with no crowd and no secret authority. State counts soundings. Sanity moves by at most one when the claim outruns the wood, or when the split steadies a frayed reading. Prose may neighbor a high whistle already in view; hooks do not read history, and nothing here is a promised event.”

<details><summary>Lua source (2817 bytes)</summary>

```lua
return {
  name = "Concord Reed",
  inspect = function(ctx)
    if ctx.charges == 0 then
      if ctx.state == 0 then
        return "The lip is dry, the split untried. Ink still says ALL AGREE, confident of a hearing it has not had."
      end
      return "Dry at the lip, split as before. ALL AGREE has not recruited a second sound. The tidy claim outlasts the breath."
    end
    if ctx.state == 0 then
      if ctx.sanity >= 70 then
        return "A thumb-dark reed, split at the lip. Ink on the grain says ALL AGREE. The hand was sure; the wood is not."
      end
      return "The split gapes past the reed's width. ALL AGREE sits beside it, and no second voice is here to make the words true."
    end
    if ctx.insight >= 200 then
      return "Same split, same four words. Another look does not summon agreement. It only makes the ink look surer than the grain."
    end
    if ctx.sanity >= 50 then
      return "The crack has not closed. Even so, ALL AGREE seems louder than the dry scrape you already know is slight."
    end
    return "You keep reading ALL AGREE as if company stood by. The reed offers only its split, and a faint high memory of scrape."
  end,
  apply = function(ctx)
    local st = ctx.state
    local text
    local delta = 0
    if st < 255 then
      st = st + 1
    end
    if ctx.state == 0 then
      if ctx.sanity >= 60 and ctx.insight < 100 then
        text = "You set the reed to your lip. It scrapes high and thin, not the agreed note. The miss is small, and hard to leave alone."
        delta = -1
      elseif ctx.sanity < 40 then
        text = "A high thin scrape, then silence. The ink looks written by a steadier hand. Only the split stays, ordinary and exact."
        delta = 1
      else
        text = "The reed answers with a slight high scrape. ALL AGREE does not arrive with it. You are left holding the discrepancy."
        delta = 0
      end
    elseif ctx.insight >= 500 then
      text = "The sounding matches the last scrape, not the inscription. Confidence supplied the agreement the wood never held."
      if ctx.sanity < 80 then
        delta = 1
      end
    elseif ctx.state >= 3 then
      text = "Again the same slight pitch. Repetition has polished the assurance, not the evidence. The split keeps its own counsel."
      if ctx.sanity >= 30 then
        delta = -1
      end
    elseif ctx.charges <= 1 then
      text = "One more thin scrape, high and unshared. The words stay neat. They still have not produced a witness beside you."
      delta = -1
    else
      text = "The scrape returns at the same high pitch. Agreement feels nearer only because the claim is easier to trust than the miss."
      if ctx.insight < 50 then
        delta = -1
      end
    end
    return { text = text, state = st, sanity_delta = delta }
  end
}
```

</details>

**madman-00007**, layer `gilman` — `runs/pilot` call 80, response `a52ac5f1b852`, 203 s, admitted

Player sees: name **Pleat Tally**; inspect (start of game): “A starched linen strip, pinpricked at the hem. The pleats look even until you count them.”; first use: “You count the pleats. Fourteen, then thirteen. The pinpricks do not correct you.” (requested Sanity +0).

Continuity note: “Starch-linen pleat tally: pinpricks and pleats disagree only while counted. Inspection describes; application counts, stops, or recounts, moving state and sanity by at most two. Higher composure can close the fold. No quest or hidden cause is claimed. Supplied backtracking suggested a count revised by attention; prayer, whispers, and the recorded death are not narrated as witnessed, nor treated as status.”

<details><summary>Lua source (3635 bytes)</summary>

```lua
return {name='Pleat Tally',inspect=function(ctx) local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state if st==0 then if i==0 then return 'A starched linen strip, pinpricked at the hem. The pleats look even until you count them.' end return 'Linen and pinpricks. The evenness fails only when you begin to number it.' end if st==1 then return 'Counted once. Pleats and pinpricks differ by one, and will not say which is late.' end if st==2 then if s>=50 then return 'Folded shut, it is only linen. The mismatch is a choice you are not making.' end return 'Folded shut. The hem still seems to hold a number you did not finish.' end if st==3 then if c<=1 then return 'The fold is soft. The old disagreement waits inside, only if you ask.' end return 'Closed after a look. The counts disagreed, and you did not follow them.' end if c<=1 then return 'The crease is soft. Another count would be easy, and so would setting it down.' end if s>=50 then return 'The pleats hold still if you do not count. Attention moves the tally, not the cloth.' end if i>100 then return 'Each recount shifts the missing pleat. The linen gives no reason, only a number.' end return 'The pleats change only while you number them. Looking away returns them to cloth.' end,apply=function(ctx) local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state if st<0 then st=0 end if st>255 then st=255 end if st==0 then local d=0 if s<50 then d=-1 end if i==0 then return {text='You count the pleats. Fourteen, then thirteen. The pinpricks do not correct you.',state=1,sanity_delta=d} end return {text='The evenness looks rehearsed. Fourteen, then thirteen. Neither number settles.',state=1,sanity_delta=d} end if st==1 then if s>=50 then return {text='You fold the strip and stop. The disagreement stays unfinished, and unasked.',state=2,sanity_delta=1} end return {text='You count again. The missing pleat has moved. Your finger finds it where you start.',state=4,sanity_delta=-1} end if st==2 then if s<50 then return {text='The count takes your finger. The missing pleat is wherever you start.',state=4,sanity_delta=-1} end if c==1 then return {text='You see the old gap and close it. The linen is almost soft.',state=3,sanity_delta=0} end return {text='You see the one-pleat gap and close it before the count can travel.',state=3,sanity_delta=0} end if st==3 then if s<50 then return {text='Numbering starts before you decide to finish. One pleat is already gone.',state=4,sanity_delta=-1} end if i==0 then return {text='You watch the counts disagree, then close it. The error gets no second step.',state=3,sanity_delta=0} end return {text='You check the hem and stop. The mismatch does not become a reason.',state=3,sanity_delta=0} end if st>=255 then if s>=50 then return {text='You stop on the wrong count and set it down. The hem is only cloth again.',state=3,sanity_delta=1} end return {text='The tally will not advance. The hem repeats the same wrong count under your finger.',state=255,sanity_delta=-1} end if s>=70 then return {text='You set it down mid-count. The last number fades. Starch, thread, and your stop remain.',state=3,sanity_delta=1} end local ns=st+1 if ns>255 then ns=255 end local d=-1 if s<30 then d=-2 elseif s>=50 then d=0 end if i>500 then return {text='You number them without expecting agreement. The error moves. It explains nothing.',state=ns,sanity_delta=d} end if c==1 then return {text='You number it once more. The absent pleat slides, and the linen is nearly soft.',state=ns,sanity_delta=d} end return {text='Another count. The absent pleat slides one stitch, as if waiting for your finger.',state=ns,sanity_delta=d} end}
```

</details>

### hound

**bard-00007** — `runs/smoke` call 2, response `14797f46c8ae`, 36 s, admitted

Agrees with the hand-authored footsteps pack on 120/120 trail cases.
```lua
return function(c)
local n=#c.history
local i=n-3
if i<1 then i=1 end
local t=c.history[i]
local dx=0
local dy=0
if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
local s=c.state
if s==nil then s=0 end
s=s+1
if s>1000000 then s=0 end
return {dx=dx,dy=dy,state=s}
end
```

**bard-inherited-00023** — `runs/others` call 25, response `8d56c6539791`, 14 s, admitted

Agrees with the hand-authored footsteps pack on 120/120 trail cases.
```lua
return function(c)
local n=#c.history
local i=n-3
if i<1 then i=1 end
local t=c.history[i]
local dx=0
local dy=0
if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
local s=c.state+1
if s>1000000 then s=0 end
return {dx=dx,dy=dy,state=s}
end
```

**bard-inherited-00023** — `runs/others` call 42, response `3dd75f17d393`, 20 s, admitted

Agrees with the hand-authored footsteps pack on 120/120 trail cases.
```lua
return function(c)
  local n=#c.history
  local i=1
  if n>=4 then i=n-3 end
  local t=c.history[i]
  local dx=0
  local dy=0
  if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
  if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
  return {dx=dx,dy=dy,state=(c.state+1)%1000001}
end
```

### hound_free

**madman-00041** — `runs/others` call 74, response `325d92f6fb30`, 92 s, admitted

Agrees with the hand-authored footsteps pack on 76/120 trail cases.
```lua
return function(c)
local h=c.history
local n=0
local i=1
while i<=8 do
if h[i]==nil then break end
n=i
i=i+1
end
local st=c.state
if st<0 then st=0 end
if st>1000000 then st=1000000 end
st=st+1
if st>1000000 then st=0 end
if n<2 then return {dx=0,dy=0,state=st} end
local changed=false
if n>=3 then
local a=h[n-2]
local b=h[n-1]
local d=h[n]
if b.x-a.x~=d.x-b.x or b.y-a.y~=d.y-b.y then changed=true end
end
local lag=3
if changed then lag=6 end
local idx=n-lag
if idx<1 then idx=1 end
if idx>=n then idx=n-1 end
local g=h[idx]
local dx=0
local dy=0
if g.x>c.mx then dx=1 elseif g.x<c.mx then dx=-1 end
if g.y>c.my then dy=1 elseif g.y<c.my then dy=-1 end
if changed then
local b=h[n-1]
local d=h[n]
local nx=d.x-b.x
local ny=d.y-b.y
if nx<0 then nx=-nx end
if ny<0 then ny=-ny end
if nx~=0 then dx=0 end
if ny~=0 then dy=0 end
end
return {dx=dx,dy=dy,state=st}
end
```

**bard-inherited-00007** — `runs/others` call 67, response `f641532cde9b`, 63 s, admitted

Agrees with the hand-authored footsteps pack on 72/120 trail cases.
```lua
return function(c)
local h=c.history
local n=0
local i=1
while i<=8 do
if h==nil or h[i]==nil then break end
n=n+1
i=i+1
end
local s=c.state
if s==nil or s<0 or s>1000000 then s=0 end
s=s+1
if s>1000000 then s=0 end
if n<2 then return {dx=0,dy=0,state=s} end
local slot=n-4
if slot<1 then slot=1 end
if slot>=n then slot=n-1 end
local r=s%35
if r==0 then slot=1
elseif r==7 or r==21 then
slot=1
if n>3 then slot=2 end
end
local t=h[slot]
if t==nil then return {dx=0,dy=0,state=s} end
local dx=0
local dy=0
if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=s}
end
```

**bard-default-path-00023** — `runs/others` call 82, response `d2f9c4f48734`, 122 s, admitted

Agrees with the hand-authored footsteps pack on 32/120 trail cases.
```lua
return function(c) local st=c.state if st==nil or st<0 or st>1000000 then st=0 end st=st+1 if st>1000000 then st=0 end local h=c.history if h==nil or h[1]==nil then return {dx=0,dy=0,state=st} end local n=0 local i=1 while i<=8 do if h[i]==nil then break end n=i i=i+1 end if n<2 then return {dx=0,dy=0,state=st} end local phase=st%5 local mid=n-(n//2) if mid<1 then mid=1 end if mid>n-1 then mid=n-1 end local ox=h[1].x local oy=h[1].y local ax=h[mid].x-ox local ay=h[mid].y-oy local bx=h[n].x-ox local by=h[n].y-oy if ax<0 then ax=-ax end if ay<0 then ay=-ay end if bx<0 then bx=-bx end if by<0 then by=-by end local md=ax if ay>md then md=ay end local nd=bx if by>nd then nd=by end local idx=1 if n>=4 and md>nd and nd<=2 then idx=mid elseif phase==4 and n>=4 then idx=2 end if idx>n-1 then idx=n-1 end if idx<1 then idx=1 end local tx=h[idx].x local ty=h[idx].y if tx==c.mx and ty==c.my and idx+1<n then tx=h[idx+1].x ty=h[idx+1].y end local sx=0 local sy=0 if tx>c.mx then sx=1 elseif tx<c.mx then sx=-1 end if ty>c.my then sy=1 elseif ty<c.my then sy=-1 end local dx=0 local dy=0 if phase==0 or phase==3 then if sx~=0 then dx=sx else dy=sy end elseif phase==1 or phase==4 then if sy~=0 then dy=sy else dx=sx end else local ex=tx-c.mx local ey=ty-c.my if ex<0 then ex=-ex end if ey<0 then ey=-ey end if ex>=ey then if sx~=0 then dx=sx else dy=sy end else if sy~=0 then dy=sy else dx=sx end end end return {dx=dx,dy=dy,state=st} end
```

### next_use

**bard-00007**, families `W` — `runs/smoke` call 5, response `0b71b89d5b06`, 49 s, admitted

Grid ops: {"quiet": 84, "whistle_attention": 12}.
```lua
return {on_action = function(context)
  local s = context.state
  local next_state = s
  if next_state < 3 then next_state = next_state + 1 end
  local op = "quiet"
  if context.trigger == "W" and context.own_witnessed == "none" and s == 0 then
    op = "whistle_attention"
  end
  return {next_use_intent_v=2, op=op, state=next_state}
end}
```

**wizard-default-path-00041**, families `W` — `runs/others` call 107, response `08e89f2f6bbb`, 95 s, admitted

Grid ops: {"quiet": 72, "whistle_attention": 24}.
```lua
return {on_action=function(context) local s=context.state if context.trigger~="W" or context.variant~=0 then return {next_use_intent_v=2,op="quiet",state=s} end if context.own_witnessed=="W" or s>=2 then if s<3 then s=s+1 end return {next_use_intent_v=2,op="quiet",state=s} end return {next_use_intent_v=2,op="whistle_attention",state=s+1} end}
```

**bard-default-path-00041**, families `W` — `runs/others` call 130, response `6e0a945ae9c8`, 81 s, admitted

Grid ops: {"quiet": 80, "whistle_attention": 16}.
```lua
return {on_action=function(context)
  local st = context.state
  local op = "quiet"
  if context.trigger == "W" and context.own_witnessed ~= "W" and context.whistle_count < 3 and st < 2 then
    op = "whistle_attention"
    st = st + 1
  elseif st < 3 then
    st = st + 1
  end
  return {next_use_intent_v=2, op=op, state=st}
end}
```

### flavour

**bard-inherited-00023** — `runs/others` call 174, response `f665282dcaf1`, 14 s, admitted

Reveal shown to the player:
```
The Crawling Chaos remembers.
  Turn 1, as you arrived on a level: whisper 1 (ambient) was admitted.
    Telegraph: "A distant whisper brushes against your thoughts."
    Effect: an omen only; no rule changed.
    Delivered: yes, "The shadows lean closer." was shown with the telegraph.
    Spent at once.
  Admitted 1, delivered 1; cruelty spent 0.
  1 other candidate was refused; none took effect.
```
Epilogue returned:
```
I remember turn 1: as you arrived on a level, whisper 1, ambient, was admitted.
An omen only; no rule changed. It was spent at once.
With the telegraph, "The shadows lean closer." was shown. Admitted 1, delivered 1.
Cruelty spent 0. One other candidate was refused; none took effect.
```

**madman-00041** — `runs/others` call 195, response `0e590cea1ad7`, 22 s, admitted

Reveal shown to the player:
```
The Crawling Chaos remembers.
  Turn 1, as you arrived on a level: whisper 1 (ambient) was admitted.
    Telegraph: "A distant whisper brushes against your thoughts."
    Effect: an omen only; no rule changed.
    Delivered: yes, "The shadows lean closer." was shown with the telegraph.
    Spent at once.
  Admitted 1, delivered 1; cruelty spent 0.
```
Epilogue returned:
```
I remember the first turn, when you arrived upon a level and one ambient whisper was admitted.
It was spent at once: an omen only, and no rule was changed.
Delivered, yes: with the telegraph was shown that the shadows lean closer, and that a distant whisper brushes against your thoughts.
Admitted 1, delivered 1; cruelty spent 0.
```

**madman-00007** — `runs/others` call 161, response `f34f5e7875a7`, 31 s, admitted

Reveal shown to the player:
```
The Crawling Chaos remembers.
  Turn 1, as you arrived on a level: whisper 1 (ambient) was admitted.
    Telegraph: "A distant whisper brushes against your thoughts."
    Effect: an omen only; no rule changed.
    Delivered: yes, "The shadows lean closer." was shown with the telegraph.
    Spent at once.
  Turn 641, as you arrived on a level: whisper 2 (hunger_rate) was admitted.
    Telegraph: "An unnatural hunger coils in your stomach."
    Effect: you grew hungry twice as fast, for 24 turns.
    Delivered: no; a rule change has no separate manifestation.
    Ended: expired on turn 665.
  Admitted 2, delivered 1; cruelty spent 3.
```
Epilogue returned:
```
I remember. Turn 1 admitted an ambient whisper, omen only, spent at once.
Delivered, and shown: a distant whisper, and the shadows lean closer. No rule changed.
Turn 641 admitted hunger_rate. You grew hungry twice as fast for 24 turns; it was not delivered.
Expired on turn 665. Admitted 2, delivered 1; cruelty spent 3.
```

**bard-inherited-00041** — `runs/others` call 191, response `7afebf12700e`, 32 s, rejected: `display_bounds`

Reveal shown to the player:
```
The Crawling Chaos remembers.
  Turn 1, as you arrived on a level: whisper 1 (ambient) was admitted.
    Telegraph: "A distant whisper brushes against your thoughts."
    Effect: an omen only; no rule changed.
    Delivered: yes, "The shadows lean closer." was shown with the telegraph.
    Spent at once.
  Turn 315, as you prayed: whisper 2 (door_reluctance) was admitted.
    Telegraph: "The doors of this place seem to lean against you."
    Effect: closed doors resisted you more often, for 192 turns.
    Delivered: no; a rule change has no separate manifestation.
    Ended: expired on turn 507.
  Admitted 2, delivered 1; cruelty spent 1.
```
Epilogue returned:
```
I remember. On turn 1, as you arrived on a level, an ambient whisper was admitted: an omen only, no rule changed, spent at once.
Shown with its telegraph: The shadows lean closer.
On turn 315, as you prayed, whisper 2 (door_reluctance) was admitted. Closed doors resisted you more often for 192 turns; no separate manifestation was delivered.
It expired on turn 507. Admitted 2, delivered 1; cruelty spent 1.
```
