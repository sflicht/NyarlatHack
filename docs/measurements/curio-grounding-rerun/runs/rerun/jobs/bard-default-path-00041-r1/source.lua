return {
name="Tarnished Reed-Slip",
inspect=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local b,g,h
if t==0 then b="One rim sits duller than its mate. "
elseif t<3 then b="The dull rim looks a trace wider. "
elseif t<8 then b="You recount the dullness and dissent. "
else b="The rim will not keep one width. " end
if s>=75 and i==0 then g="A trick of polish, perhaps, or a note already refused. "
elseif s>=75 and i<100 then g="The flatness is small and repeatable. "
elseif s>=75 then g="You could name the interval, and do not. "
elseif s>=40 and i==0 then g="The eye insists; the metal does not confirm. "
elseif s>=40 and i<100 then g="A second pitch seems to wait under the first. "
elseif s>=40 then g="The interval is plain, and still unwelcome. "
elseif i==0 then g="The dull edge seems to advance without moving. "
elseif i<100 then g="The mind supplies a note the copper cannot hold. "
else g="Knowing the interval does not quiet it. " end
if c==0 then h="It will not sound."
elseif c==1 then h="One breath remains."
elseif c==2 then h="Two breaths remain."
else h="Breath is still plentiful." end
return "Copper reed-slip, thumb-dark. "..b..g..h
end,
apply=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if c==0 then
return {text="The slip takes no breath. The dull rim stays as it was.",state=t,sanity_delta=0}
end
local ns=t+1
if ns>255 then ns=255 end
local head,d,tail
if t==0 then head="Breath across the slip comes back flat. "
elseif t<3 then head="Again the breath returns a hair flat. "
elseif t<8 then head="The flatness arrives before the breath ends. "
else head="You already know the flatness, and test it. " end
if s>=80 and i>=100 and t>=3 and c>1 then
d=1
tail="The interval is named, and the jaw eases."
elseif s>=80 and c==1 then
d=-1
tail="Even a steady hand keeps this last miss."
elseif s>=80 and t==0 then
d=-1
tail="The miss is slight, and it will not leave."
elseif s>=80 then
d=0
tail="You file the miss beside the others."
elseif s>=50 and c==1 then
d=-2
tail="The last breath fixes the flatness in the teeth."
elseif s>=50 and i==0 then
d=-1
tail="No reason offers itself for the miss."
elseif s>=50 and i>=100 then
d=0
tail="You place the interval. The miss remains."
elseif s>=50 then
d=-1
tail="A second tone rides the first, unasked."
elseif i>=100 and c>1 then
d=0
tail="The interval keeps its name, and nothing yields."
elseif s<25 or c==1 then
d=-2
tail="The copper seems to finish the note for you."
else
d=-1
tail="The dull rim feels nearer than the metal allows."
end
return {text=head..tail,state=ns,sanity_delta=d}
end
}
