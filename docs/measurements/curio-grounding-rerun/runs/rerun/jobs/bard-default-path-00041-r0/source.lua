return {
name='Fissured Pitch-Pipe',
inspect=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if c==0 and st==0 then
return 'The pipe is cold at the lip. The split is only a line. No tone offers itself, yet you listen.'
end
if st==0 then
if s>=80 and i==0 then
return 'Ebony pitch-pipe, hairline split at the lip. A high tone gathers and fails. You will not swear you heard it.'
elseif s>=80 then
return 'The split sits wrong against the grain. A high tone starts in the pipe and seems to finish elsewhere.'
else
return 'The mouthpiece crack looks wider than a hair. You lean in. It is a hair again. Your eyes disagree.'
end
elseif st==1 then
return 'Where you pressed, the split holds a pale burr. The high tone, if it was one, arrived a half-breath late.'
elseif st==2 then
if s<50 then
return 'The crack resembles a small mouth. You know that is only shape. You look again to be certain.'
else
return 'You check the crack twice. It has not widened. Still the second tone seems to prefer the late beat.'
end
elseif c==0 then
return 'The pipe is light, the split unchanged. Whatever note you expect, the wood offers only the crack.'
elseif s<40 then
return 'The doubled tone is not sounding, yet you arrange your mouth for it. The crack waits, patient and blank.'
elseif s>=80 then
return 'You have measured the split by eye and by tongue. Both measures agree, and neither satisfies.'
elseif i>=100 then
return 'The interval will not name its source. The pipe is only ebony, split, and colder at the lip than the hand.'
else
return 'A high, unfinished interval clings to the split. You cannot decide which half you would correct.'
end
end,
apply=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local ns=st+1
if ns>255 then ns=255 end
local text,d
if st==0 then
if s>=80 and i==0 then
text='You sound a high tone. It splits: one in the pipe, one flatter from the crack. You claim only the first.'
d=-1
elseif s>=80 then
text='The high tone leaves the pipe clean and seems to finish past the split. You cannot point to where.'
d=-1
else
text='You mean one high note. Two arrive, and the flatter one feels more like yours. That cannot be right.'
d=-1
if s<40 then d=-2 end
end
elseif st==1 then
if s<60 then
text='The late note is already in your mouth. You stop. The crack looks innocent, which does not help.'
d=-2
else
text='You match the true tone. The flatter one arrives first. The burr at the split was not there before you checked.'
d=-1
end
elseif st==2 then
if i>0 then
text='You end early. The second tone has no place you can point to. The split does not explain it.'
d=-1
else
text='You end the tone early. The missing half hangs. For a breath the air seems tuned a step too low.'
d=-1
end
elseif s<40 then
text='You sound the interval you fear. Both tones arrive. Neither feels like the one you chose.'
d=-2
elseif s>=75 and c>1 then
text='You force one clean high note and hold it. Breath steadies. The crack still answers a shade flat.'
d=1
elseif s>=75 then
text='One thin high note, barely held. It steadies nothing. The split keeps the flatter reply.'
d=-1
elseif i>=50 then
text='The high tone is yours. The flat echo is not placed. You lower the pipe and the echo stops late.'
d=-1
else
text='You play the note once more, carefully. It is single. A moment later it is not. You heard both.'
d=-1
end
return {text=text,state=ns,sanity_delta=d}
end
}
