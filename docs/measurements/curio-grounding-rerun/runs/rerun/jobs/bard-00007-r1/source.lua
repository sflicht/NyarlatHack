return {
name='Contrary Reed',
inspect=function(ctx)
local s,c,san,ins=ctx.state,ctx.charges,ctx.sanity,ctx.insight
if c==0 then
if s%2==0 then
return 'Spent, it is whole. A whole reed has no split, yet the split is what you are holding.'
end
return 'Shut from the far end. The far end was the near end. Neither end kept the sound.'
end
if s%2==0 then
if san>=50 then
if c==3 then
return 'A pale reed split for a bard. The grain runs to the mouth, so the note must arrive before the breath.'
end
return 'The grain has crept a fraction toward the mouth. A fraction is not a direction, yet the note would still have to arrive first.'
end
return 'Pale, split, and sure of neither. You hold the mouth end. The mouth end is the far end. It will not choose.'
end
if ins==0 then
return 'Turned once, the label faces in. It reads OUT. The unseen face must therefore read IN. You have not turned it.'
end
return 'Read backward, the grain leaves the mouth. The note, already spent, was only the silence counted twice.'
end,
apply=function(ctx)
local s,c,san,ins=ctx.state,ctx.charges,ctx.sanity,ctx.insight
local ns,delta,text=s,0,'Nothing answers. The reed agrees, which is the same as disagreeing, and the air stays put.'
if c==0 then
return {text=text,state=ns,sanity_delta=delta}
end
if s<255 then ns=s+1 else ns=0 end
if c==1 then
if s%2==0 then
text='Last breath in. It leaves by the entrance. The exit is where you started, which is not a place.'
delta=-1
else
text='Last breath the other way. It arrives where it began, one count early, and calls that punctual.'
if san<50 then delta=-1 else delta=0 end
end
elseif s%2==0 then
if san>=70 then
text='You blow. Silence comes first, exact as a receipt, and the note follows it out of order.'
delta=-1
else
text='You blow into the near end. The near end sends the breath back as if it had been the instruction.'
if san<40 then delta=-1 else delta=0 end
end
else
if ins>200 then
text='Blown backward, the note is the silence counted once. Counting it twice would make it shorter, so you stop.'
delta=1
elseif san<35 then
text='The other way gives a note that left before you began. What remains is two breaths short of a sound.'
delta=-2
else
text='You blow the other way. The note is already gone. What remains is shorter than the breath that missed it.'
delta=0
end
end
return {text=text,state=ns,sanity_delta=delta}
end
}