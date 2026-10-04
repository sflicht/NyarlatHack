local function inspect(ctx)
  local s,san,ins,ch=ctx.state,ctx.sanity,ctx.insight,ctx.charges
  if s==0 then
    if ch==0 then
      return "A pale reed, split on the grain. No breath seems welcome. The crack is dry, narrow, and too easy to recount."
    elseif ins>500 then
      return "A pale reed, split on the grain. You reach for a history of the crack and find none. It is dry. That should be enough."
    elseif san>=70 then
      return "A pale reed, split along the grain. The crack is dry and narrow. You are not sure it was always this slight."
    end
    return "The split looks wider than the reed can spare. You blink, and it is only a pale crack again. You blink once more."
  end
  if ins>500 and san<45 then
    return "You invent the split's cause and feel the invention fray. The high note you remember has nowhere to sit but the crack."
  end
  if ins>500 then
    return "You fit a cause to the darkened split, then mistrust the fit. The reed gives you damp wood and nothing you can prove."
  end
  if san<45 then
    return "The split seems to hold a high note. A crack cannot hold a note. Your eye returns, and the fancy returns with it."
  end
  if ch==0 then
    return "The reed takes nothing from a look. The split stays dark, and counting its ridges does not finish the count."
  end
  if ch<2 then
    return "You hesitate over another breath. The split is darker where the last one went. Under the thumb it is only a line."
  end
  if s<3 then
    return "Moisture darkens the split. The last tone, too high by a little, hangs in the ear though the reed is silent."
  end
  return "You have worried this crack before. It looks no wider, and yet your thumb expects a gap the wood does not give."
end
local function apply(ctx)
  local s,san,ins,ch=ctx.state,ctx.sanity,ctx.insight,ctx.charges
  local ns=s+1
  if ns>255 then ns=255 end
  local text,delta
  if ch==0 then
    text="You lift the reed and no breath takes. The split neither widens nor answers. The silence is only silence."
    delta=0
    ns=s
  elseif s==0 then
    if ins==0 and san>=80 then
      text="You draw breath across the split. A thin note rises, a shade too high, and stops when you stop. Only that."
      delta=0
    elseif ins>200 then
      text="The note leaves your mouth already high. You nearly name why. The name fails, and the pitch does not."
      delta=-1
    else
      text="Breath across the split gives a thin, high note, not the one you shaped. The crack is warm for a moment."
      delta=-1
    end
  elseif s<4 then
    if san>=85 and san<100 and ch>1 then
      text="You force the pitch down to the tone you meant. It holds. You are steadier, and you distrust the steadiness."
      delta=1
    elseif san>=85 and ch>1 then
      text="You force the pitch down to the tone you meant. It holds. You are no steadier for it, and the distrust remains."
      delta=0
    elseif san<40 then
      text="The high note arrives before the breath is finished. You did not ask for it. The wood is warmer than it should be."
      delta=-2
    else
      text="Again the tone rides high of your intent. You blame the crack. The blame fits, slips, and fits too well."
      delta=-1
    end
  elseif ins==0 then
    text="Grain, moisture, a split. Still the tone lifts higher than the last. You keep no reason, only the rise."
    delta=-1
  elseif san<30 then
    text="You know the error and produce it sooner. The split does not teach. It repeats, higher, and will not be corrected."
    delta=-2
  else
    text="The wrong high note is in the air as your lip touches wood. Attention made it sharper, not truer."
    delta=-1
  end
  return {text=text,state=ns,sanity_delta=delta}
end
return {name="Pale Split Reed",inspect=inspect,apply=apply}
