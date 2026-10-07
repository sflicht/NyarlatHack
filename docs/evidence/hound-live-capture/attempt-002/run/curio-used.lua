return {
name="Pale Reed Case",
inspect=function(ctx)
local s,n,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if t==0 then
if s>=70 then return "Lacquer lies flat. A dried reed sits in the groove, pale as cut paper."
elseif s>=40 then return "The lid sheen hesitates under the thumb. The reed is only dry."
else return "The reed fibers are counted twice. The second count will not agree." end
elseif t==1 then
if n>=200 then return "A hairline crosses the lid. By eye it is wider than a breath ago."
elseif s>=50 then return "A hairline crosses the lid. It may have been missed. That seems unlikely."
else return "The hairline is present when looked at, and nearer when looked at again." end
elseif t==2 then
if c<=1 then return "The reed has a damp edge. The mouth is dry. Those facts will not meet."
else return "One fiber on the reed is darker, as if a breath touched it and stayed." end
else
if s<30 then return "The case is shut. A small click remains, though the hand has not moved."
elseif n>500 then return "The hairline has not grown. That it stays exactly so is the worse fact."
else return "Shut, it seems to keep a thin sound: too slight for a note, too exact for wind." end
end
end,
apply=function(ctx)
local s,n,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local nxt,d,text=t,0,""
if c==0 then return {text="The case stays shut under the thumb. No further answer offers itself.",state=t,sanity_delta=0} end
if nxt<255 then nxt=nxt+1 end
if t==0 then
if s>=80 then text="The lid shuts. The reed was dry. Certainty about that is almost complete." d=0
elseif s>=30 then text="Breath crosses the reed and leaves no tone. The lacquer takes a faint line." d=-1
else text="One breath, and no tone. The silence seems to have been already there." d=-2 end
elseif t==1 then
if n>=200 then text="The hairline is set against a memory of its width. The memory loses."
else text="The hairline takes the thumb. It is no deeper. It is checked again anyway." end
d=-1
elseif t==2 then
if c==1 then text="The hinge is stiff. A darker fiber remains, and the lid will not unmark it."
else text="A darker fiber marks the reed. Closing the case does not unmark it." end
if s<40 then d=-2 else d=-1 end
else
if n>500 then text="The width is the same as last time. Exact sameness is not a comfort."
elseif c==1 then text="The hinge is stiff. The reed gives back only the same dry, disputed edge."
else text="Nothing new opens. The same thin discrepancy is all the case will give." end
if s>=90 then d=0 elseif s<25 then d=-2 else d=-1 end
end
return {text=text,state=nxt,sanity_delta=d}
end
}
