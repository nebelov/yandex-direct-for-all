# Competitor Research Workflow

Использовать, когда нужно системно собрать и разобрать рекламные сообщения конкурентов.

## Принцип

Сбор материалов можно автоматизировать браузером. Анализ содержания - только вручную мной по сохранённым raw-артефактам.

## Шаги

1. Определить список конкурентов и площадок.
   Примеры: Google Ads Transparency, Meta Ad Library, LinkedIn, каталоги, лендинги, YouTube preroll examples.
2. Собрать raw-материалы.
   - скриншоты;
   - текст объявлений;
   - URL лендингов;
   - дата/источник.
3. Сохранить raw локально.
   Рекомендуемая структура:
   - `research/competitors/raw/<brand>/screenshots/`
   - `research/competitors/raw/<brand>/ads.tsv`
   - `research/competitors/raw/<brand>/landing_notes.md`
4. Выполнить ручной анализ по шаблону:
   - angle;
   - ICP / segment;
   - JTBD;
   - promise;
   - proof;
   - CTA;
   - offer;
   - risk-reversal;
   - visual pattern;
   - what NOT to copy.
5. Сформировать итог:
   - themes matrix;
   - positioning gaps;
   - creative hypotheses;
   - taboo list;
   - reusable lessons for own ads.

## Что запрещено

- копировать креативы и тексты конкурентов;
- делать выводы без сохранённых raw-артефактов;
- использовать analysis-скрипты для automatic scoring объявлений.

## Рекомендуемый выход

- `research/competitors/summary.md`
- `research/competitors/themes.tsv`
- `research/competitors/hypotheses.md`
