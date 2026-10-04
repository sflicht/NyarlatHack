return {name="Contrary Palm Rule",inspect=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if st>=255 then return "Both ends are worn smooth. The numbers have been counted off the rule."
elseif st>=3 and c==0 then return "Only scratches remain, and nothing further is offered. Each is first and last."
elseif st>=3 then return "The marks have thinned to scratches. Each still claims to be first and last."
elseif c==0 and i==0 then return "Handled to its limit, it still offers zero at both ends, as a courtesy."
elseif c==0 then return "Handled to its limit, it keeps a length measured from an end it will not choose."
elseif i==0 and s>=80 and st==0 then return "A palm-length ivory rule. Zero sits at each end, so the middle is halfway and nowhere."
elseif i==0 and s>=80 and st==1 then return "It still fits the palm. One turn has made both zeros a little more convinced."
elseif i==0 and s>=80 and st==2 then return "Turned twice, it agrees with itself by refusing both directions at once."
elseif i==0 and s<50 then return "Cool ordinary ivory. The numbers add downward and call that downward sum a start."
elseif i==0 then return "Palm ivory, neatly ruled. One end says zero; the other says zero, correcting it."
elseif i>500 and s>=50 then return "You can name the fault. The zeros do not move. They stay, politely, in two places."
elseif s<40 then return "The discrepancy is exact. You pick an end, and it turns out to have been the other."
else return "Each mark is one inch from the last and one inch from the first. Both claims fit."
end
end,apply=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local ns,d,t=st,0,"."
if st<255 then ns=st+1 end
if st>=255 then t="Nothing further shifts. It is already as long as a directionless thing can be."; d=0
elseif st==0 and i==0 and s>=80 then t="Laid on the palm, both zeros stay. The inch between them declines to be one."; d=-1
elseif st==0 and i==0 and s<40 then t="Against the skin it reads two ways at once, and the quarrel outlasts the ivory."; d=-2
elseif st==0 and i==0 then t="Set to the skin, it reads forward and back, and calls the quarrel a fair measure."; d=-1
elseif st==0 and i>100 and s<99 then t="You correct one zero. The other accepts the correction and, fairly, becomes first."; d=1
elseif st==0 then t="You try to fix one end. The untouched end agrees too quickly, and spoils the fix."; d=0
elseif c==0 then t="The gesture finds nothing left to turn. The zeros trade places, then stop."; d=0
elseif i>500 and s>=50 and s<99 then t="The reversal is legible. It steadies the hand, and neither zero agrees to move."; d=1
elseif st>=2 and c==1 and s<50 then t="The last inch cancels. What remains points at the end you would not call the start."; d=-2
elseif st>=2 and c==1 then t="The last inch cancels. Left behind is a length aimed at the end you did not pick."; d=-1
elseif s<30 then t="Turned again, it grows shorter in sense and longer in being precisely wrong."; d=-2
elseif i==0 then t="End for end, it reads the same refusal backwards, and seems pleased to match."; d=-1
elseif s>=90 then t="Read the other way, the logic reverses cleanly. The ivory stays cool in the hand."; d=0
else t="Read the other way, the contradiction folds shut, then opens by one narrow doubt."; d=-1
end
return {text=t,state=ns,sanity_delta=d}
end}