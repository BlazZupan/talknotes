# Copy Text from the Notes

Talknotes was also built for prompt-engineering classes: keep longer prompts on the slide, copy them, paste into the chatbot. No retyping.

* pressing **`c`** copies the text from all the quoted blocks on the slide to the clipboard
* **`m` then 1–9** copies the n-th quoted block to the clipboard
* **`[` / `]`** make quoted text smaller or larger

Quoted text is anything written in an input markdown file that starts with a blockquote (`>`).

# Copy the Whole Prompt

Press **`c`**, then paste into a chatbot. This is one prompt from a lecture on finding citations.

> In the following, I will give you the scientific text. You will:
> - Identify the sentences that require citation
> - For each such sentence, you will propose one citation. The citation has to be recent (since 2015) and verified (use PubMed search)
>
> You output should follow the following pattern:
> **Sentence**: (a sentence to find the citation for)
> **Citation**: (detailed citation in APA7 format)
> **Links**: (PubMED ID), (DOI)
> **Sentence with citation**: (sentence where citation appears in the format (Smith et al., 2026))
>
> Note: citation does not need to be at the end of the sentence but rather, and better, where it is most appropriate. Make sure you do not cite the same paper more than once.
>
> In my next prompt, I will give you the text, you will find the citations and do what I asked you above, ask me if the output is correct and make any changes if required, and then we will repeat the process with the next text. OK?

# Copy Only One Quoted Example

Several prompts on one slide: press **`m`**, then **`1`**, **`2`**, or **`3`**. Paste, then try the same claim on each role.

> Act as a skeptic who is well-versed in biotechnology. Whatever I tell you, provide a short, skeptical and scientific response.

> Act as a naive, average person with no access to science who is skeptical about everything that science does. Provide a short, ironic, and negative response to everything I will tell you. Ok?

> Act as a hyperactive, very positive person. Whatever I tell you, provide a short, encouraging answer, and (randomly) put some emojis. Construct an answer such person would use in Twitter/X.

Try copying this last quote to the keyboard:

> We can solve the problem of climate change by planting fast-growing trees in Brazil.
