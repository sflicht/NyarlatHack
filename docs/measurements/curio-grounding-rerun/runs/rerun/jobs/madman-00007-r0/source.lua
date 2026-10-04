return {
name='The Twice-Faced Tag',
inspect=function(ctx)
if ctx.state%2==0 then
if ctx.state==0 then
if ctx.insight==0 then
return 'A small paper tag, creased once. Both faces read THIS SIDE UP. They cannot both be.'
elseif ctx.insight<100 then
return 'Ordinary paper, one crease. Each face claims to be up, so neither claim can stand.'
else
return 'Only paper. Read twice, each face denies the position that would make the other true.'
end
elseif ctx.sanity<50 then
return 'It is crease-up again, if again is the word. Both ups remain, and neither yields.'
else
return 'Back to the first face, or a face like it. THIS SIDE UP has not chosen a side.'
end
elseif ctx.sanity>=70 then
return 'Turned over, it still reads THIS SIDE UP. The paper is cooler. The crease points down.'
elseif ctx.charges==0 then
return 'The turned tag lies still. THIS SIDE UP is printed. The fold offers no further motion.'
else
return 'The same line faces you. You are less sure which side was up before the turn.'
end
end,
apply=function(ctx)
local st=ctx.state
local nxt=st
local d=0
local t
if st%2==0 then
nxt=st+1
if nxt>255 then nxt=255 end
if st==0 and ctx.sanity>=70 and ctx.insight==0 then
d=-1
t='You turn the tag. THIS SIDE UP meets you again. This side is cooler, which settles nothing.'
elseif st==0 and ctx.sanity<40 then
d=1
t='You turn it and the instruction is already satisfied. The ease is small and poorly earned.'
elseif st==0 then
d=-1
t='You turn it. The sentence is identical, which is not the same thing as unchanged.'
elseif ctx.insight>500 then
d=-2
t='You turn it onto a face the crease has already shown. The neatness leaves a thin chill.'
else
d=0
t='You turn it as though starting. The crease was already waiting on the far side.'
end
else
nxt=st-1
if nxt<0 then nxt=0 end
if ctx.insight>500 then
d=-2
t='Turned back, it was never the other way. The fit is too neat and leaves a thin chill.'
elseif ctx.charges>1 then
d=0
t='You turn it back. It was already that way. The fold disagrees, without raising its voice.'
elseif ctx.sanity<50 then
d=-1
t='You turn it back. The words stay. You are the part that does not match the instruction.'
else
d=1
t='You set the tag the first way. Leaving it and turning it feel equally finished.'
end
end
return {text=t,state=nxt,sanity_delta=d}
end
}