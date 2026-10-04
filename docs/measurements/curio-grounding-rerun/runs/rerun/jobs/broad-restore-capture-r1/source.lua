return {
name='Assent Slip',
inspect=function(ctx)
local s=ctx.sanity
local n=ctx.insight
local c=ctx.charges
local t=ctx.state
if c==0 then
return 'The ink has faded to a rumor of a word. It still holds the shape of a conclusion.'
elseif n>=500 then
return 'One word and no particulars. The hand is confident. The scrap cannot support the confidence.'
elseif t==0 and c==3 and s>=80 then
return 'The ink looks newly dry, as if agreement were recent. You have no memory to match it.'
elseif t==0 and s>=90 and n==0 then
return 'A narrow slip, clerk-neat: AGREED. No note of any sound heard, only that the matter is closed.'
elseif t==0 and s<50 then
return 'AGREED, in heavy strokes. The word seems to lean toward you, though the slip lies flat.'
elseif t==0 then
return 'Thumb-sized paper. One sure word, AGREED, and no note of who, or of what was heard.'
elseif t==1 then
return 'The face says AGREED. The back says nothing. Between them, a confidence with no contents.'
elseif t<5 then
return 'Creased now. The word survives the crease, which is more than the evidence does.'
else
return 'Worried smooth, it still reads AGREED. Repetition has not supplied a missing reason.'
end
end,
apply=function(ctx)
local s=ctx.sanity
local n=ctx.insight
local c=ctx.charges
local t=ctx.state
local ns=255
local text
local d
if t<255 then ns=t+1 end
if t>=255 then
text='No new crease will take. AGREED stays small, finished, and unproven.'
d=0
elseif t==0 and c>=2 then
text='Fresh ink, and the word AGREED. You find no bargain it could be closing, and no sound it records.'
d=-1
elseif t==0 then
text='You press the slip. AGREED does not yield. A sure account, and nothing beside it to trust.'
d=0
elseif t==1 then
text='The reverse is blank. Whatever was agreed left no terms, only this confident face.'
if s>=50 then d=0 else d=-1 end
elseif t==2 and n==0 then
text='With nothing to set against it, the word steadies you. The paper remains embarrassingly small.'
d=1
elseif t==2 then
text='You can name no second party. AGREED still reads as settled. The modesty of the scrap rebukes it.'
d=-1
elseif s>=80 and n<20 then
text='You nearly sign on with the hand that wrote it. Nearly. Ink is not a witness.'
d=1
elseif s<40 and n>50 then
text='The word feels rehearsed, worn smooth by repetition you cannot place. Only the slip is here.'
d=-2
elseif c<=1 then
text='The ink is thinning. The conclusion is not. You still cannot say what was agreed.'
d=-1
elseif s<50 then
text='AGREED looks written for you. That is absurd. The slip bears no name, not even yours.'
d=-1
else
text='You read it once more. The account does not grow. Your doubt does, by a very little.'
d=0
end
return {text=text,state=ns,sanity_delta=d}
end
}
