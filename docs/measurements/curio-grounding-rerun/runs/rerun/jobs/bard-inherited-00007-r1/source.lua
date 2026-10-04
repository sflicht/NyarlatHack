return{name="Twice-Counted Hem",inspect=function(ctx)
local s=ctx.state%5
if s==0 then
if ctx.sanity>=60 then
return "Undyed hem, palm-wide. Twelve stitches along the edge. Counted again: eleven."
end
return "The hem lies flat, yet the count will not. Twelve, then eleven, under a steady eye."
elseif s==1 then
if ctx.insight>=40 then
return "The fault is a doubled thread, not a missing stitch. Naming it does not fix the sum."
end
return "Starting from the other end changes nothing. The hem offers two totals and keeps both."
elseif s==2 then
if ctx.charges<=1 then
return "The edge looks handled thin. Whatever number you settle on, the next glance revises it."
end
return "A loose fiber lifts with your breath and lies down elsewhere. You did not choose the place."
elseif s==3 then
if ctx.sanity<35 then
return "The pattern seems to lean. You cannot tell whether the lean is in the cloth or the eye."
end
return "Against the light the weave is only linen. The disagreement does not leave with the shadow."
else
if ctx.insight>500 then
return "The same small error repeats at a fixed interval. What the interval serves, you cannot say."
end
return "The fault meets you again. It looks planned, then only tired, then planned once more."
end
end,apply=function(ctx)
local s=ctx.state%5
local nxt=(ctx.state+1)%256
local text,delta
if s==0 then
text="You count to twelve. The last stitch is not there. The hem remains ordinary cloth."
delta=-1
elseif s==1 then
if ctx.insight>=20 then
text="You press the doubled thread flat. It stays. The two totals do not become one."
delta=0
else
text="You choose one end and call it first. The far end keeps a count of its own."
delta=-1
end
elseif s==2 then
if ctx.sanity>=80 then
text="You stop at eleven and refuse the recount. For a moment the edge agrees."
delta=1
else
text="You stop at eleven. A blink later the twelfth stitch is back, or the first is gone."
delta=-1
end
elseif s==3 then
if ctx.charges==0 then
text="Nothing answers the press of your thumb. The hem is cloth, and the count is still wrong."
delta=0
else
text="Your thumb finds the raised stitch. It is only thread. You are less sure of the number."
delta=-1
end
else
text="You look away, then back. The hem has not moved. The count has, by one, again."
if ctx.sanity>=90 then delta=0 else delta=-1 end
end
return{text=text,state=nxt,sanity_delta=delta}
end}
